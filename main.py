from __future__ import annotations

import argparse
import asyncio
import contextlib
from contextlib import AsyncExitStack

from livestudio.app import VTubeStudioApp
from livestudio.services import AudioSourceKind, AudioStreamRouter
from livestudio.services.animations import AnimationManager
from livestudio.services.expressions import (
    BUILTIN_EXPRESSION_UNITS,
    EmotionKind,
    EmotionRequest,
    ExpressionSelector,
)
from livestudio.services.platforms.vtubestudio import (
    default_vtube_studio_parameter_specs,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.semantic_actions import SemanticActionAdapter
from livestudio.utils.log import StatusLine, logger


def _format_level_bar(level: float, *, width: int = 24) -> str:
    """将 $[0, 1]$ 区间的电平值格式化为文本条"""

    clamped_level = max(0.0, min(1.0, level))
    filled = round(clamped_level * width)
    return "█" * filled + "·" * (width - filled)


async def _cancel_and_await(task: asyncio.Task[object]) -> None:
    """取消后台任务并等待它完成退出。"""

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def monitor_audio_stream(audio_stream: AudioStreamRouter) -> None:
    """持续读取当前活动音频流并原地显示实时音量信息"""

    status_line = StatusLine()
    subscription = audio_stream.subscribe(queue_maxsize=8)
    try:
        while True:
            chunk = await asyncio.wait_for(subscription.queue.get(), timeout=5.0)
            rms, peak = chunk.analysis.rms, chunk.analysis.peak
            status_line.update(
                f"[AUDIO:{audio_stream.active_source_kind}] "
                f"RMS={rms:.4f} {_format_level_bar(rms)} | "
                f"PEAK={peak:.4f} {_format_level_bar(peak)} | "
                f"overflowed={chunk.overflowed}",
            )
    finally:
        audio_stream.unsubscribe(subscription)
        status_line.finish()


def _parse_emotion_vector(raw_values: list[str]) -> dict[EmotionKind, float]:
    emotions: dict[EmotionKind, float] = {}
    for raw_value in raw_values:
        if "=" in raw_value:
            raw_name, raw_weight = raw_value.split("=", 1)
            weight = float(raw_weight)
        else:
            raw_name = raw_value
            weight = 1.0
        emotions[EmotionKind(raw_name.strip().lower())] = weight
    return emotions or {EmotionKind.JOY: 1.0}


def _build_emotion_request(args: argparse.Namespace) -> EmotionRequest:
    return EmotionRequest(
        emotions=_parse_emotion_vector(args.emotion),
        intent=args.intent,
        intensity=args.intensity,
        randomness=args.randomness,
        duration_scale=args.duration_scale,
    )


def _log_selected_expression(
    selected,
    adapter: SemanticActionAdapter,
) -> None:
    logger.info(
        "[AU] score={:.3f}, intent_match={:.3f}, expression_strength={:.3f}, intent={}, tags={}",
        selected.score,
        selected.intent_match,
        selected.expression_strength,
        selected.intent_id or "-",
        ",".join(sorted(selected.semantic_tags)) or "-",
    )
    for unit in selected.units:
        logger.info(
            "[AU] {} -> {} targets={}",
            "/".join(sorted(region.value for region in unit.regions)),
            unit.id,
            len(unit.targets),
        )
    for target in selected.targets:
        states = adapter.resolve(target)
        if not states:
            logger.warning(
                "[AU] {}={:.3f} 未找到可用语义映射",
                target.action,
                target.value,
            )
            continue
        for state in states:
            logger.info(
                "[AU] {}={:.3f} -> {} {:.3f}->{:.3f}",
                target.action,
                target.value,
                state.name,
                state.start_value,
                state.value,
            )


async def preview_au_system(args: argparse.Namespace) -> None:
    """在不连接 VTS 的情况下预览 AU 选择与默认语义映射"""

    profile = default_vtube_studio_semantic_profile()
    adapter = SemanticActionAdapter(
        profile,
        parameter_specs=default_vtube_studio_parameter_specs(),
    )
    selector = ExpressionSelector(BUILTIN_EXPRESSION_UNITS, profile)
    request = _build_emotion_request(args)
    selected = selector.preview(request)
    _log_selected_expression(selected, adapter)


async def test_au_system(args: argparse.Namespace) -> None:
    """连接 VTS 并触发一次情绪驱动 AU 表情"""

    audio_stream = AudioStreamRouter()
    animation_manager = AnimationManager()
    vtubestudio_app = VTubeStudioApp(
        animation_manager=animation_manager,
        audio_stream=audio_stream,
    )

    try:
        await vtubestudio_app.initialize()
        await vtubestudio_app.start_platform_for_expression_test()
        request = _build_emotion_request(args)
        selected = vtubestudio_app.expression_service.preview(request)
        adapter = vtubestudio_app.platform.semantic_adapter
        if adapter is None:
            raise RuntimeError("当前平台未实现 AU 语义映射")
        _log_selected_expression(
            selected,
            adapter,
        )
        await vtubestudio_app.expression_service.express(request)
        logger.info("[AU] 已触发表情，保持 {:.2f} 秒", args.hold)
        await asyncio.sleep(args.hold)
    finally:
        await vtubestudio_app.stop()
        await audio_stream.stop()


async def main() -> None:
    audio_stream = AudioStreamRouter()
    animation_manager = AnimationManager()
    vtubestudio_app = VTubeStudioApp(
        animation_manager=animation_manager,
        audio_stream=audio_stream,
    )

    async with AsyncExitStack() as stack:
        await stack.enter_async_context(audio_stream)
        await stack.enter_async_context(vtubestudio_app)
        await audio_stream.switch_source(AudioSourceKind.MICROPHONE)
        audio_task = asyncio.create_task(monitor_audio_stream(audio_stream))
        stack.push_async_callback(_cancel_and_await, audio_task)
        logger.info("[OK] 通用音频流监听已启动，按 Ctrl+C 退出程序")
        await asyncio.Event().wait()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LiveStudio")
    parser.add_argument(
        "--au-preview",
        action="store_true",
        help="只预览 AU 选择和默认语义映射，不连接 VTube Studio",
    )
    parser.add_argument(
        "--au-test",
        action="store_true",
        help="连接 VTube Studio，加载当前模型并触发一次 AU 表情",
    )
    parser.add_argument(
        "--emotion",
        action="append",
        default=[],
        help="情绪名称或 name=weight，可以重复写；每个情绪独立 0~1，比如 --emotion joy=0.9 --emotion anger=0.7",
    )
    parser.add_argument(
        "--intent",
        default=None,
        help="指定组合表情意图，比如 阴险笑、苦笑、委屈",
    )
    parser.add_argument("--intensity", type=float, default=0.7, help="表情强度 0~1")
    parser.add_argument(
        "--randomness",
        type=float,
        default=0.25,
        help="组合随机度 0~1",
    )
    parser.add_argument(
        "--duration-scale",
        type=float,
        default=1.0,
        help="动作时长倍率",
    )
    parser.add_argument("--hold", type=float, default=1.2, help="AU 测试后保持秒数")
    return parser


if __name__ == "__main__":
    cli_args = _build_parser().parse_args()
    try:
        if cli_args.au_preview:
            asyncio.run(preview_au_system(cli_args))
        elif cli_args.au_test:
            asyncio.run(test_au_system(cli_args))
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

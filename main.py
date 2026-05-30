from __future__ import annotations

import argparse
import asyncio
import contextlib

from livestudio.app import VTubeStudioApp
from livestudio.services import AudioSourceKind, AudioStreamRouter
from livestudio.services.animations import AnimationManager
from livestudio.services.expressions import (
    BUILTIN_EXPRESSION_UNITS,
    CalibrationProfile,
    EmotionKind,
    EmotionRequest,
    ExpressionSelector,
)
from livestudio.utils.log import StatusLine, logger


def _format_level_bar(level: float, *, width: int = 24) -> str:
    """将 $[0, 1]$ 区间的电平值格式化为文本条。"""

    clamped_level = max(0.0, min(1.0, level))
    filled = round(clamped_level * width)
    return "█" * filled + "·" * (width - filled)


async def monitor_audio_stream(audio_stream: AudioStreamRouter) -> None:
    """持续读取当前活动音频流并原地显示实时音量信息。"""

    status_line = StatusLine()
    subscription = audio_stream.subscribe(queue_maxsize=8)
    try:
        while True:
            chunk = await asyncio.wait_for(subscription.queue.get(), timeout=5.0)
            rms, peak = chunk.analysis.rms, chunk.analysis.peak
            status_line.update(
                "[AUDIO:{}] RMS={:.4f} {} | PEAK={:.4f} {} | overflowed={}".format(
                    audio_stream.active_source_kind,
                    rms,
                    _format_level_bar(rms),
                    peak,
                    _format_level_bar(peak),
                    chunk.overflowed,
                ),
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
        intensity=args.intensity,
        randomness=args.randomness,
        duration_scale=args.duration_scale,
        allow_none_regions=not args.no_none_regions,
    )


def _log_selected_expression(
    selected,
    calibration: CalibrationProfile,
) -> None:
    logger.info(
        "[AU] score={:.3f}, emotion_match={:.3f}",
        selected.score,
        selected.emotion_match,
    )
    for region, unit in selected.units.items():
        logger.info(
            "[AU] {} -> {} targets={} tags={}",
            region,
            unit.id,
            len(unit.targets),
            ",".join(sorted(unit.tags)) or "-",
        )
    for target in selected.targets:
        states = calibration.resolve(target.semantic_param, target.value)
        if not states:
            logger.warning(
                "[AU] {}={:.3f} 未找到可用校准",
                target.semantic_param,
                target.value,
            )
            continue
        for state in states:
            logger.info(
                "[AU] {}={:.3f} -> {} {:.3f}->{:.3f}",
                target.semantic_param,
                target.value,
                state.name,
                state.start_value,
                state.value,
            )


async def preview_au_system(args: argparse.Namespace) -> None:
    """在不连接 VTS 的情况下预览 AU 选择与默认校准映射。"""

    calibration = CalibrationProfile.with_defaults()
    selector = ExpressionSelector(BUILTIN_EXPRESSION_UNITS, calibration)
    request = _build_emotion_request(args)
    selected = selector.preview(request)
    _log_selected_expression(selected, calibration)


async def test_au_system(args: argparse.Namespace) -> None:
    """连接 VTS 并触发一次情绪驱动 AU 表情。"""

    audio_stream = AudioStreamRouter()
    animation_manager = AnimationManager()
    vtubestudio_app = VTubeStudioApp(
        animation_manager=animation_manager,
        audio_stream=audio_stream,
    )

    try:
        await vtubestudio_app.initialize()
        await vtubestudio_app.platform.start()
        await vtubestudio_app._subscribe_model_events()
        await vtubestudio_app._load_active_model_config()
        request = _build_emotion_request(args)
        selected = vtubestudio_app.expression_service.preview(request)
        _log_selected_expression(
            selected,
            vtubestudio_app.expression_service.calibration,
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

    await audio_stream.initialize()
    await vtubestudio_app.initialize()

    audio_task: asyncio.Task[None] | None = None

    try:
        await audio_stream.start()
        await vtubestudio_app.start()
        await audio_stream.switch_source(AudioSourceKind.MICROPHONE)
        audio_task = asyncio.create_task(monitor_audio_stream(audio_stream))
        logger.info("[OK] 通用音频流监听已启动，按 Ctrl+C 退出程序")
        await asyncio.Event().wait()

    finally:
        if audio_task is not None:
            audio_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await audio_task
        await vtubestudio_app.stop()
        await audio_stream.stop()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LiveStudio")
    parser.add_argument(
        "--au-preview",
        action="store_true",
        help="只预览 AU 选择和默认校准映射，不连接 VTube Studio。",
    )
    parser.add_argument(
        "--au-test",
        action="store_true",
        help="连接 VTube Studio，加载当前模型并触发一次 AU 表情。",
    )
    parser.add_argument(
        "--emotion",
        action="append",
        default=[],
        help="情绪名称或 name=weight，可重复，例如 --emotion joy=0.8 --emotion sadness=0.2。",
    )
    parser.add_argument("--intensity", type=float, default=0.7, help="表情强度 0~1。")
    parser.add_argument(
        "--randomness",
        type=float,
        default=0.25,
        help="组合随机度 0~1。",
    )
    parser.add_argument(
        "--duration-scale",
        type=float,
        default=1.0,
        help="动作时长倍率。",
    )
    parser.add_argument("--hold", type=float, default=1.2, help="AU 测试后保持秒数。")
    parser.add_argument(
        "--no-none-regions",
        action="store_true",
        help="禁止选择空区域单元，强制四个区域都有动作。",
    )
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

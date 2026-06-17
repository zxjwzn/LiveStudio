from __future__ import annotations

import asyncio
import contextlib
from contextlib import AsyncExitStack

from livestudio.app import VTubeStudioApp
from livestudio.services import AudioSourceKind, AudioStreamRouter
from livestudio.services.animations import AnimationManager
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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

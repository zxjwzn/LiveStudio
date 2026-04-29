from __future__ import annotations

import asyncio
import contextlib

import numpy as np

from livestudio.app import VTubeStudioApp
from livestudio.log import StatusLine, logger
from livestudio.services import AudioChunk, AudioSourceKind, AudioStreamRouter
from livestudio.services.animations import AnimationManager


def _format_level_bar(level: float, *, width: int = 24) -> str:
    """将 $[0, 1]$ 区间的电平值格式化为文本条。"""

    clamped_level = max(0.0, min(1.0, level))
    filled = round(clamped_level * width)
    return "█" * filled + "·" * (width - filled)


def _describe_audio_chunk(chunk: AudioChunk) -> tuple[float, float]:
    """计算音频块的 RMS 与峰值强度。"""

    samples = np.asarray(chunk.data, dtype=np.float32)
    if samples.size == 0:
        return 0.0, 0.0

    flattened = samples.reshape(-1)
    rms = float(np.sqrt(np.mean(np.square(flattened))))
    peak = float(np.max(np.abs(flattened)))
    return rms, peak


async def monitor_audio_stream(audio_stream: AudioStreamRouter) -> None:
    """持续读取当前活动音频流并原地显示实时音量信息。"""

    status_line = StatusLine()
    try:
        while True:
            chunk = await audio_stream.read_chunk(timeout=5.0)
            rms, peak = _describe_audio_chunk(chunk)
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
        status_line.finish()


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


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

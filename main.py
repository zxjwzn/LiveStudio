from __future__ import annotations

import asyncio
import contextlib

import numpy as np

from livestudio.log import logger
from livestudio.services import AudioChunk, AudioInputService
from livestudio.services.vtubestudio import ModelExpressionSyncService, VTubeStudio
from livestudio.services.vtubestudio.subservices.animation_runtime import (
    AnimationRuntimeService,
)


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


async def monitor_microphone(audio_service: AudioInputService) -> None:
    """持续读取麦克风输入并打印实时音量信息。"""

    while True:
        chunk = await audio_service.read_chunk(timeout=5.0)
        rms, peak = _describe_audio_chunk(chunk)
        logger.info(
            "[MIC] RMS={:.4f} {} | PEAK={:.4f} {} | overflowed={}",
            rms,
            _format_level_bar(rms),
            peak,
            _format_level_bar(peak),
            chunk.overflowed,
        )


async def main() -> None:
    vtubestudio_service = VTubeStudio(
        subservices=[
            AnimationRuntimeService(),
            ModelExpressionSyncService(),
        ],
    )
    audio_service = AudioInputService()

    await vtubestudio_service.initialize()
    await audio_service.initialize()

    logger.info(
        "[MIC] 已选择输入设备: {} ({})，channels={}, samplerate={}",
        audio_service.device_info.name,
        audio_service.device_info.index,
        audio_service.config.channels,
        audio_service.config.samplerate or int(audio_service.device_info.default_samplerate),
    )

    audio_task: asyncio.Task[None] | None = None

    try:
        await vtubestudio_service.start()
        await audio_service.start()
        audio_task = asyncio.create_task(monitor_microphone(audio_service))
        logger.info("[OK] 已连接并认证 VTS，麦克风监听已启动，按 Ctrl+C 退出程序")

        await asyncio.Event().wait()
    finally:
        if audio_task is not None:
            audio_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await audio_task
        await audio_service.close()
        await vtubestudio_service.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

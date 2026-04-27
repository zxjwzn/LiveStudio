from __future__ import annotations

import asyncio
import contextlib

import numpy as np

from livestudio.log import logger
from livestudio.services import (
    AudioSourceKind,
    AudioStreamRouter,
)
from livestudio.services.platforms.vtubestudio import VTubeStudio


async def main() -> None:
    audio_stream = AudioStreamRouter()
    vtubestudio_service = VTubeStudio()

    await audio_stream.initialize()
    await vtubestudio_service.initialize()

    try:
        await audio_stream.start()
        await vtubestudio_service.start()
        await audio_stream.switch_source(AudioSourceKind.MICROPHONE)
        await asyncio.Event().wait()

    finally:
        await audio_stream.stop()
        await vtubestudio_service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

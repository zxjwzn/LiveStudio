from __future__ import annotations

import asyncio
import contextlib

import numpy as np

from livestudio.log import logger
from livestudio.services import (
    AudioSourceKind,
    AudioStreamRouter,
)
from livestudio.services.vtubestudio import VTubeStudio


async def main() -> None:
    vtubestudio_service = VTubeStudio()
    audio_stream = AudioStreamRouter()

    await vtubestudio_service.initialize()
    await audio_stream.initialize()

    try:
        await vtubestudio_service.start()
        await audio_stream.start()
        await audio_stream.switch_source(AudioSourceKind.MICROPHONE)
        await asyncio.Event().wait()
    finally:
        await vtubestudio_service.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

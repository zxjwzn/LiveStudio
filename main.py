from __future__ import annotations

import asyncio
import contextlib

import numpy as np

from livestudio.log import logger
from livestudio.services import (
    AudioSourceKind,
    AudioStreamRouter,
)
from livestudio.services.animations import AnimationManager
from livestudio.services.platforms.vtubestudio import VTubeStudio


async def main() -> None:
    audio_stream = AudioStreamRouter()
    vtubestudio_service = VTubeStudio()
    animation_manager = AnimationManager()
    animation_manager.register_runtime(vtubestudio_service)

    await audio_stream.initialize()
    await vtubestudio_service.initialize()
    await animation_manager.initialize()

    try:
        await audio_stream.start()
        await vtubestudio_service.start()
        await animation_manager.start()
        await vtubestudio_service.subscribe_model_loaded(
            animation_manager.apply_vtubestudio_model_config,
        )
        current_model_config = await vtubestudio_service.reload_current_model_config()
        if current_model_config is not None:
            await animation_manager.apply_vtubestudio_model_config(
                current_model_config,
            )
        await audio_stream.switch_source(AudioSourceKind.MICROPHONE)
        await asyncio.Event().wait()

    finally:
        await animation_manager.stop()
        await audio_stream.stop()
        await vtubestudio_service.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

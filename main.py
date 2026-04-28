from __future__ import annotations

import asyncio

from livestudio.app import VTubeStudioApp
from livestudio.log import logger
from livestudio.services import AudioSourceKind, AudioStreamRouter
from livestudio.services.animations import AnimationManager


async def main() -> None:
    audio_stream = AudioStreamRouter()
    animation_manager = AnimationManager()
    vtubestudio_app = VTubeStudioApp(
        animation_manager=animation_manager,
        audio_stream=audio_stream,
    )

    await audio_stream.initialize()
    await vtubestudio_app.initialize()

    try:
        await audio_stream.start()
        await vtubestudio_app.start()
        await audio_stream.switch_source(AudioSourceKind.MICROPHONE)
        await asyncio.Event().wait()

    finally:
        await vtubestudio_app.stop()
        await audio_stream.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

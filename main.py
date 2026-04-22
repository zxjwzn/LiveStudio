from __future__ import annotations

import asyncio

from livestudio.log import logger
from livestudio.services.vtubestudio import VTubeStudio
from livestudio.services.vtubestudio.subservices.animation_runtime import (
    AnimationRuntimeService,
)


async def main() -> None:
    vtubestudio_service = VTubeStudio(subservices=[AnimationRuntimeService()])
    await vtubestudio_service.initialize()

    try:
        await vtubestudio_service.start()
        await vtubestudio_service.stop_subservices()
        await vtubestudio_service.animation_runtime.play_template(
            "smile",
        )
        
        #await vtubestudio_service.tween.tween(
        #    parameter_name="EyeOpenLeft",
        #    end_value=0.0,
        #    duration=0.3,
        #    easing="in_out_sine",
        #    priority=3,
        #    keep_alive=True,
        #)
        logger.info("[OK] 已连接并认证 VTS，并已测试播放模板 wink，按 Ctrl+C 退出程序")

        await asyncio.Event().wait()
    finally:
        await vtubestudio_service.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

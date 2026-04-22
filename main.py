from __future__ import annotations

import asyncio

from livestudio.log import logger
from livestudio.services.vtubestudio import ModelExpressionSyncService, VTubeStudio
from livestudio.services.vtubestudio.subservices.animation_runtime import (
    AnimationRuntimeService,
)


async def main() -> None:
    vtubestudio_service = VTubeStudio(
        subservices=[
            AnimationRuntimeService(),
            ModelExpressionSyncService(),
        ],
    )
    await vtubestudio_service.initialize()

    try:
        await vtubestudio_service.start()
        logger.info("[OK] 已连接并认证 VTS，模型表情同步已启动，按 Ctrl+C 退出程序")

        await asyncio.Event().wait()
    finally:
        await vtubestudio_service.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

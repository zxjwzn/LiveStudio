from __future__ import annotations

import asyncio

from livestudio.log import logger
from livestudio.services.vtubestudio import VTubeStudio


async def main() -> None:
    vtubestudio_service = VTubeStudio()
    await vtubestudio_service.initialize()

    try:
        await vtubestudio_service.start()

        logger.info("[OK] 已连接并认证 VTS，按 Ctrl+C 退出程序")

        await asyncio.Event().wait()
    finally:
        await vtubestudio_service.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[OK] 收到 Ctrl+C，程序已退出")

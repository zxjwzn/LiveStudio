from __future__ import annotations

import asyncio

from livestudio import Easing
from livestudio.services.vtubestudio import VTubeStudio


async def main() -> None:
    parameter_name = "FaceAngleX"
    service = VTubeStudio()
    await service.initialize()

    try:
        await service.client.connect()
        authentication_token = service.config.authentication_token

        if authentication_token is None:
            authentication_token = await service.request_authentication_token()
            service.config.authentication_token = authentication_token
            await service.config_manager.save()

        authenticated = await service.client.authenticate(authentication_token)
        if not authenticated:
            raise RuntimeError("VTube Studio 认证失败")

        service.tween.start()

        print("[OK] 已连接并认证 VTS")
        print(f"[OK] 开始测试参数: {parameter_name}")

        await service.tween.tween(
            parameter_name=parameter_name,
            start_value=0.0,
            end_value=15.0,
            duration=0.3,
            easing=Easing.out_sine,
            keep_alive=False,
        )
        await service.tween.tween(
            parameter_name=parameter_name,
            start_value=15.0,
            end_value=-15.0,
            duration=0.3,
            easing=Easing.out_sine,
            keep_alive=False,
        )
        await service.tween.tween(
            parameter_name=parameter_name,
            start_value=-15.0,
            end_value=0.0,
            duration=0.3,
            easing=Easing.out_sine,
            keep_alive=False,
        )

        await service.tween.release(parameter_name)
        print("[OK] tween 测试完成")
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())

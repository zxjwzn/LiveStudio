"""Example usage snippets for the async VTube Studio client library."""

from __future__ import annotations

from .client import VTubeStudioClient
from .config import VTubeStudioConfig, VTubeStudioPluginInfo
from .models import (
    ColorTintRequest,
    ColorTintRequestData,
    HotkeysInCurrentModelRequest,
    HotkeysInCurrentModelRequestData,
    ItemListRequest,
    ItemListRequestData,
    MoveModelRequest,
    MoveModelRequestData,
    ParameterCreationRequest,
    ParameterCreationRequestData,
)
from .models.common import ArtMeshMatcher, ColorTint
from .service import VTubeStudioService


async def build_service() -> VTubeStudioService:
    """构建服务实例。

    使用说明：
    1. 将 `plugin_name` 和 `plugin_developer` 替换为你的插件信息。
    2. 如果用户修改了 VTube Studio 端口，请同步修改 `port`。
    3. 先调用 `request_authentication_token()` 获取令牌，再保存并复用。
    """

    config = VTubeStudioConfig(port=8001)
    plugin_info = VTubeStudioPluginInfo(
        plugin_name="LiveStudio",
        plugin_developer="Zaxpris",
    )
    client = VTubeStudioClient(config=config, plugin_info=plugin_info)
    return VTubeStudioService(client)


async def example_connect_and_authenticate(authentication_token: str) -> bool:
    """连接并认证。

    参数:
        authentication_token: 之前通过用户授权获得的持久令牌。

    返回:
        是否连接并认证成功。
    """

    service = await build_service()
    return await service.connect_and_authenticate(authentication_token)


async def example_request_authentication_token() -> str:
    """首次接入时申请令牌。"""

    service = await build_service()
    await service.client.connect()
    return await service.request_authentication_token()


async def example_move_model() -> None:
    """将当前模型移动到屏幕中央偏上位置。"""

    service = await build_service()
    request = MoveModelRequest(
        data=MoveModelRequestData(
            timeInSeconds=0.2,
            valuesAreRelativeToModel=False,
            positionX=0.0,
            positionY=0.35,
            rotation=0.0,
            size=-20.0,
        ),
    )
    await service.move_model(request)


async def example_list_hotkeys() -> list[str]:
    """获取当前模型的热键名称列表。"""

    service = await build_service()
    response = await service.get_hotkeys(
        HotkeysInCurrentModelRequest(data=HotkeysInCurrentModelRequestData()),
    )
    return [hotkey.name for hotkey in response.data.available_hotkeys]


async def example_create_custom_parameter() -> str:
    """创建一个自定义输入参数。"""

    service = await build_service()
    response = await service.create_parameter(
        ParameterCreationRequest(
            data=ParameterCreationRequestData(
                parameterName="MoodLevel",
                explanation="用于控制开心程度的自定义参数。",
                min=0.0,
                max=1.0,
                defaultValue=0.0,
                ),
            ),
    )
    return response.data.parameter_name


async def example_list_scene_items() -> int:
    """读取当前场景中的道具数量。"""

    service = await build_service()
    response = await service.get_items(
        ItemListRequest(
            data=ItemListRequestData(
                includeAvailableSpots=False,
                includeItemInstancesInScene=True,
                includeAvailableItemFiles=False,
                ),
            ),
    )
    return response.data.items_in_scene_count


async def example_tint_model() -> int:
    """将名称包含 `eye` 的 ArtMesh 着为暖色。"""

    service = await build_service()
    response = await service.tint_art_meshes(
        ColorTintRequest(
            data=ColorTintRequestData(
                colorTint=ColorTint(
                    colorR=255,
                    colorG=180,
                    colorB=120,
                    colorA=255,
                    mixWithSceneLightingColor=1.0,
                ),
                artMeshMatcher=ArtMeshMatcher(
                    tintAll=False,
                    nameContains=["eye"],
                ),
            ),
        ),
    )
    return response.data.matched_art_meshes

"""VTube Studio 服务"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable
from pathlib import Path

from livestudio.config import ConfigManager
from livestudio.log import logger
from livestudio.tween import ControlledParameterState, ParameterTweenEngine, TweenMode

from ..clients.vtube_studio.client import VTubeStudioClient
from ..clients.vtube_studio.config import VTubeStudioConfig
from ..clients.vtube_studio.discovery import VTubeStudioDiscovery
from ..clients.vtube_studio.event_listener import VTSEventListener
from ..clients.vtube_studio.event_manager import ListenerHandler, VTSEventManager
from ..clients.vtube_studio.models import (
    APIStateResponse,
    ArtMeshListResponse,
    ArtMeshSelectionRequest,
    ArtMeshSelectionResponse,
    ColorTintRequest,
    ColorTintResponse,
    CurrentModelResponse,
    EventSubscriptionRequest,
    EventSubscriptionResponse,
    ExpressionActivationRequest,
    ExpressionActivationResponse,
    ExpressionStateRequest,
    ExpressionStateResponse,
    FaceFoundResponse,
    GetCurrentModelPhysicsResponse,
    HotkeysInCurrentModelRequest,
    HotkeysInCurrentModelResponse,
    HotkeyTriggerRequest,
    HotkeyTriggerResponse,
    InjectParameterDataRequest,
    InjectParameterDataRequestData,
    InjectParameterDataResponse,
    InjectParameterValue,
    InputParameterListResponse,
    ItemAnimationControlRequest,
    ItemAnimationControlResponse,
    ItemListRequest,
    ItemListResponse,
    ItemLoadRequest,
    ItemLoadResponse,
    ItemMoveRequest,
    ItemMoveResponse,
    ItemPinRequest,
    ItemPinResponse,
    ItemSortRequest,
    ItemSortResponse,
    ItemUnloadRequest,
    ItemUnloadResponse,
    Live2DParameterListResponse,
    ModelLoadRequest,
    ModelLoadResponse,
    MoveModelRequest,
    MoveModelResponse,
    NDIConfigRequest,
    NDIConfigResponse,
    ParameterCreationRequest,
    ParameterCreationResponse,
    ParameterDeletionRequest,
    ParameterDeletionResponse,
    ParameterValueRequest,
    ParameterValueResponse,
    PermissionRequest,
    PermissionResponse,
    PostProcessingListRequest,
    PostProcessingListResponse,
    PostProcessingUpdateRequest,
    PostProcessingUpdateResponse,
    SceneColorOverlayInfoResponse,
    SetCurrentModelPhysicsRequest,
    SetCurrentModelPhysicsResponse,
    StatisticsResponse,
    VTSFolderInfoResponse,
    VTubeStudioAPIStateBroadcast,
)


class VTubeStudio:
    """对外暴露稳定业务接口的服务层。"""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        config_manager: ConfigManager[VTubeStudioConfig] | None = None,
        tween_keep_alive_interval: float = 0.5,
        tween_default_fps: int = 60,
    ) -> None:
        self.config_manager = config_manager or ConfigManager(
            VTubeStudioConfig,
            Path(config_path) if config_path is not None else Path("config") / "vtube_studio.yaml",
        )
        self._client: VTubeStudioClient | None = None
        self._events: VTSEventManager | None = None
        self._discovery: VTubeStudioDiscovery | None = None
        self.tween = ParameterTweenEngine(
            self._send_parameter_states,
            keep_alive_interval=tween_keep_alive_interval,
            default_fps=tween_default_fps,
        )

    @property
    def config(self) -> VTubeStudioConfig:
        """返回最新配置快照。"""

        return self.config_manager.config

    @property
    def client(self) -> VTubeStudioClient:
        """返回已初始化的底层客户端。"""

        return self._require_client()

    @property
    def events(self) -> VTSEventManager:
        """返回已初始化的事件管理器。"""

        return self._require_events()

    @property
    def discovery(self) -> VTubeStudioDiscovery:
        """返回已初始化的 discovery 实例。"""

        return self._require_discovery()

    async def initialize(self) -> None:
        """加载配置并创建内部依赖。"""

        await self.config_manager.load()
        client = VTubeStudioClient(
            config=self.config_manager.config,
            plugin_info=self.config_manager.config.plugin,
        )
        self._client = client
        self._events = VTSEventManager(client, client.config.event_queue_size)
        self._discovery = VTubeStudioDiscovery(client.config)

    def _require_client(self) -> VTubeStudioClient:
        client = self._client
        if client is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return client

    def _require_events(self) -> VTSEventManager:
        events = self._events
        if events is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return events

    def _require_discovery(self) -> VTubeStudioDiscovery:
        discovery = self._discovery
        if discovery is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return discovery

    async def close(self) -> None:
        """释放该服务持有的后台资源。"""

        await self.tween.close()
        await self.config_manager.save()
        client = self._client
        self._client = None
        self._events = None
        self._discovery = None
        if client is not None:
            await client.disconnect()

    async def connect_and_authenticate(self, authentication_token: str | None = None) -> bool:
        """连接到 VTube Studio 并执行认证流程。

        Returns:
            bool: 连接和认证是否成功。

        Raises:
            VTubeStudioConnectionError: 连接失败。
            AuthenticationError: 认证失败。
            APIError: VTS 返回 API 错误。
            ResponseError: 请求超时或响应错误。
        """

        if authentication_token is None:
            logger.error("未提供 authentication_token，无法完成会话认证")
            return False

        try:
            client = self._require_client()
            await client.connect()
            return await client.authenticate(authentication_token)
        except Exception:
            logger.exception("连接并认证失败")
            with contextlib.suppress(Exception):
                await self._require_client().disconnect()
            return False

    async def reconnect(self, authentication_token: str) -> bool:
        """重新建立连接并进行认证。"""

        with contextlib.suppress(Exception):
            await self._require_client().disconnect()
        return await self.connect_and_authenticate(authentication_token)

    async def request_authentication_token(self) -> str:
        """向用户申请新的持久认证令牌。"""

        return await self._require_client().request_token()

    async def get_api_state(self) -> APIStateResponse:
        """查询 API 运行状态与当前会话认证状态。"""

        return await self._require_client().get_api_state()

    async def get_statistics(self) -> StatisticsResponse:
        """获取运行时统计信息。"""

        return await self._require_client().get_statistics()

    async def get_permissions(self) -> PermissionResponse:
        """查询当前插件权限状态。"""

        return await self._require_client().get_permissions()

    async def request_permission(self, request: PermissionRequest) -> PermissionResponse:
        """向用户申请指定权限。"""

        return await self._require_client().request_permission(request)

    async def get_folder_info(self) -> VTSFolderInfoResponse:
        """获取 VTS 关键目录名称。"""

        return await self._require_client().get_folder_info()

    async def get_current_model(self) -> CurrentModelResponse:
        """获取当前加载模型详情。"""

        return await self._require_client().get_current_model()

    async def load_model(self, request: ModelLoadRequest) -> ModelLoadResponse:
        """加载或卸载模型。"""

        return await self._require_client().load_model(request)

    async def move_model(self, request: MoveModelRequest) -> MoveModelResponse:
        """移动当前模型。"""

        return await self._require_client().move_model(request)

    async def get_hotkeys(self, request: HotkeysInCurrentModelRequest) -> HotkeysInCurrentModelResponse:
        """获取当前模型、指定模型或 Live2D 道具的热键列表。"""

        return await self._require_client().get_hotkeys(request)

    async def trigger_hotkey(self, request: HotkeyTriggerRequest) -> HotkeyTriggerResponse:
        """触发热键。"""

        return await self._require_client().trigger_hotkey(request)

    async def get_expression_state(self, request: ExpressionStateRequest) -> ExpressionStateResponse:
        """获取表达式状态。"""

        return await self._require_client().get_expression_state(request)

    async def set_expression_active(self, request: ExpressionActivationRequest) -> ExpressionActivationResponse:
        """激活或关闭表达式。"""

        return await self._require_client().set_expression_active(request)

    async def get_art_meshes(self) -> ArtMeshListResponse:
        """获取当前模型所有 ArtMesh。"""

        return await self._require_client().get_art_meshes()

    async def tint_art_meshes(self, request: ColorTintRequest) -> ColorTintResponse:
        """为指定 ArtMesh 应用颜色覆盖。"""

        return await self._require_client().tint_art_meshes(request)

    async def get_scene_color_overlay_info(self) -> SceneColorOverlayInfoResponse:
        """获取场景光照叠加状态。"""

        return await self._require_client().get_scene_color_overlay_info()

    async def is_face_found(self) -> FaceFoundResponse:
        """检查当前追踪器是否检测到人脸。"""

        return await self._require_client().is_face_found()

    async def get_input_parameters(self) -> InputParameterListResponse:
        """获取默认和自定义输入参数。"""

        return await self._require_client().get_input_parameters()

    async def get_parameter_value(self, request: ParameterValueRequest) -> ParameterValueResponse:
        """获取单个参数值。"""

        return await self._require_client().get_parameter_value(request)

    async def get_live2d_parameters(self) -> Live2DParameterListResponse:
        """获取当前模型的全部 Live2D 参数。"""

        return await self._require_client().get_live2d_parameters()

    async def create_parameter(self, request: ParameterCreationRequest) -> ParameterCreationResponse:
        """创建或覆盖自定义参数。"""

        return await self._require_client().create_parameter(request)

    async def delete_parameter(self, request: ParameterDeletionRequest) -> ParameterDeletionResponse:
        """删除自定义参数。"""

        return await self._require_client().delete_parameter(request)

    async def inject_parameter_data(self, request: InjectParameterDataRequest) -> InjectParameterDataResponse:
        """注入参数跟踪数据。"""

        return await self._require_client().inject_parameter_data(request)

    async def get_current_model_physics(self) -> GetCurrentModelPhysicsResponse:
        """读取当前模型物理设置。"""

        return await self._require_client().get_current_model_physics()

    async def set_current_model_physics(self, request: SetCurrentModelPhysicsRequest) -> SetCurrentModelPhysicsResponse:
        """覆盖当前模型物理设置。"""

        return await self._require_client().set_current_model_physics(request)

    async def get_ndi_config(self, request: NDIConfigRequest) -> NDIConfigResponse:
        """查询或设置 NDI 配置。"""

        return await self._require_client().get_ndi_config(request)

    async def get_items(self, request: ItemListRequest) -> ItemListResponse:
        """获取场景道具与可加载道具列表。"""

        return await self._require_client().get_items(request)

    async def load_item(self, request: ItemLoadRequest) -> ItemLoadResponse:
        """加载道具到场景。"""

        return await self._require_client().load_item(request)

    async def unload_item(self, request: ItemUnloadRequest) -> ItemUnloadResponse:
        """从场景卸载道具。"""

        return await self._require_client().unload_item(request)

    async def control_item_animation(self, request: ItemAnimationControlRequest) -> ItemAnimationControlResponse:
        """控制道具动画、亮度和透明度。"""

        return await self._require_client().control_item_animation(request)

    async def move_items(self, request: ItemMoveRequest) -> ItemMoveResponse:
        """批量移动道具。"""

        return await self._require_client().move_items(request)

    async def sort_item(self, request: ItemSortRequest) -> ItemSortResponse:
        """设置道具在模型中的前后层级。"""

        return await self._require_client().sort_item(request)

    async def select_art_meshes(self, request: ArtMeshSelectionRequest) -> ArtMeshSelectionResponse:
        """请求用户在 VTS 中选择 ArtMesh。"""

        return await self._require_client().select_art_meshes(request)

    async def pin_item(self, request: ItemPinRequest) -> ItemPinResponse:
        """将道具固定到模型。"""

        return await self._require_client().pin_item(request)

    async def get_post_processing(self, request: PostProcessingListRequest) -> PostProcessingListResponse:
        """获取后处理系统状态、预设与效果。"""

        return await self._require_client().get_post_processing(request)

    async def update_post_processing(self, request: PostProcessingUpdateRequest) -> PostProcessingUpdateResponse:
        """更新后处理配置。"""

        return await self._require_client().update_post_processing(request)

    async def subscribe_event(self, request: EventSubscriptionRequest) -> EventSubscriptionResponse:
        """订阅事件。"""

        return await self._require_events().subscribe(request)

    async def unsubscribe_event(self, event_name: str | None = None) -> EventSubscriptionResponse:
        """退订事件。"""

        return await self._require_events().unsubscribe(event_name)

    def add_event_handler(self, event_name: str, handler: ListenerHandler) -> None:
        """添加事件回调。"""

        self._require_events().add_handler(event_name, handler)

    def remove_event_handler(self, event_name: str, handler: ListenerHandler) -> None:
        """移除事件回调。"""

        self._require_events().remove_handler(event_name, handler)

    def create_event_listener(self, event_name: str) -> VTSEventListener:
        """创建队列型事件监听器。"""

        return self._require_events().create_listener(event_name)

    def remove_event_listener(self, listener: VTSEventListener) -> None:
        """移除队列型事件监听器。"""

        self._require_events().remove_listener(listener)

    async def discover_api(self, timeout: float | None = None) -> VTubeStudioAPIStateBroadcast:
        """等待一条 UDP 广播。"""

        return await self._require_discovery().discover_once(timeout)

    async def listen_for_api(
        self,
        timeout: float | None = None,
        max_messages: int | None = None,
    ) -> list[VTubeStudioAPIStateBroadcast]:
        """监听一组 UDP 广播并返回结果。"""

        broadcasts: list[VTubeStudioAPIStateBroadcast] = []
        async for broadcast in self._require_discovery().listen(timeout=timeout, max_messages=max_messages):
            broadcasts.append(broadcast)
        return broadcasts

    async def _send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: TweenMode,
    ) -> None:
        parameter_states = list(states)
        if not parameter_states:
            return

        request = InjectParameterDataRequest(
            data=InjectParameterDataRequestData(
                mode=mode,
                parameterValues=[InjectParameterValue(id=state.name, value=state.value) for state in parameter_states],
            ),
        )
        await self.inject_parameter_data(request)

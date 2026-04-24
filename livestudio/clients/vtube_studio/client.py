"""用于 VTube Studio 公共 API 的异步 WebSocket 客户端。"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, cast

from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from .config import VTubeStudioConfig, VTubeStudioPluginInfo
from .errors import (
    APIError,
    AuthenticationError,
    EventDispatchError,
    ResponseError,
    VTubeStudioConnectionError,
)
from .models import (
    APIStateRequest,
    APIStateResponse,
    ArtMeshListRequest,
    ArtMeshListResponse,
    ArtMeshSelectionRequest,
    ArtMeshSelectionResponse,
    AuthenticationRequest,
    AuthenticationRequestData,
    AuthenticationResponse,
    AuthenticationTokenRequest,
    AuthenticationTokenRequestData,
    AuthenticationTokenResponse,
    AvailableModelsRequest,
    AvailableModelsResponse,
    ColorTintRequest,
    ColorTintResponse,
    CurrentModelRequest,
    CurrentModelResponse,
    EventSubscriptionConfig,
    EventSubscriptionRequest,
    EventSubscriptionRequestData,
    EventSubscriptionResponse,
    ExpressionActivationRequest,
    ExpressionActivationResponse,
    ExpressionStateRequest,
    ExpressionStateResponse,
    FaceFoundRequest,
    FaceFoundResponse,
    GetCurrentModelPhysicsRequest,
    GetCurrentModelPhysicsResponse,
    HotkeysInCurrentModelRequest,
    HotkeysInCurrentModelResponse,
    HotkeyTriggerRequest,
    HotkeyTriggerResponse,
    InjectParameterDataRequest,
    InjectParameterDataResponse,
    InputParameterListRequest,
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
    Live2DParameterListRequest,
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
    SceneColorOverlayInfoRequest,
    SceneColorOverlayInfoResponse,
    SetCurrentModelPhysicsRequest,
    SetCurrentModelPhysicsResponse,
    StatisticsRequest,
    StatisticsResponse,
    VTSAPIErrorEnvelope,
    VTSEventEnvelope,
    VTSFolderInfoRequest,
    VTSFolderInfoResponse,
    VTSRequestEnvelope,
    VTSResponseEnvelope,
)

ResponseT = TypeVar("ResponseT", bound=VTSResponseEnvelope[Any])
EventHandler = Callable[[VTSEventEnvelope], Awaitable[None] | None]


class VTubeStudioClient:
    """基于 WebSocket 的异步 VTube Studio API 客户端。"""

    def __init__(
        self,
        config: VTubeStudioConfig,
        plugin_info: VTubeStudioPluginInfo,
    ) -> None:
        self.config = config
        self.plugin_info = plugin_info
        self._connection: ClientConnection | None = None
        self._lock = asyncio.Lock()
        self._pending_requests: dict[str, asyncio.Future[str]] = {}
        self._reader_task: asyncio.Task[None] | None = None
        self._event_handlers: dict[str, list[EventHandler]] = {}
        self._event_subscriptions: dict[str, EventSubscriptionRequest] = {}

    @property
    def is_connected(self) -> bool:
        """当前是否已建立 WebSocket 连接。"""

        return (
            self._connection is not None
            and self._reader_task is not None
            and not self._reader_task.done()
        )

    async def connect(self) -> None:
        """建立到 VTube Studio 的 WebSocket 连接。"""

        if self._connection is not None:
            return

        try:
            self._connection = await asyncio.wait_for(
                connect(
                    self.config.websocket_url,
                    user_agent_header=self.config.user_agent,
                    open_timeout=self.config.connect_timeout,
                    close_timeout=self.config.connect_timeout,
                    max_size=4 * 1024 * 1024,
                ),
                timeout=self.config.connect_timeout,
            )
            self._reader_task = asyncio.create_task(self._reader_loop())
        except (OSError, TimeoutError, WebSocketException) as exc:
            self._connection = None
            raise VTubeStudioConnectionError(
                f"无法连接到 {self.config.websocket_url}",
            ) from exc

    async def disconnect(self) -> None:
        """关闭 WebSocket 连接。"""

        connection = self._connection
        reader_task = self._reader_task
        self._connection = None
        self._reader_task = None
        if connection is None:
            return

        if reader_task is not None:
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task

        try:
            await connection.close()
        except WebSocketException as exc:
            raise VTubeStudioConnectionError("关闭 VTube Studio 连接失败") from exc
        finally:
            self._fail_pending_requests(
                VTubeStudioConnectionError("VTube Studio 连接已关闭"),
            )

    async def request_token(self) -> str:
        """请求插件认证令牌。"""

        request = AuthenticationTokenRequest(
            data=AuthenticationTokenRequestData(
                pluginName=self.plugin_info.plugin_name,
                pluginDeveloper=self.plugin_info.plugin_developer,
                pluginIcon=self.plugin_info.plugin_icon,
            ),
        )
        response = await self.send_request(request, AuthenticationTokenResponse)
        return response.data.authentication_token

    async def authenticate(self, authentication_token: str) -> bool:
        """使用令牌认证当前会话。"""

        request = AuthenticationRequest(
            data=AuthenticationRequestData(
                pluginName=self.plugin_info.plugin_name,
                pluginDeveloper=self.plugin_info.plugin_developer,
                authenticationToken=authentication_token,
            ),
        )
        response = await self.send_request(request, AuthenticationResponse)
        if not response.data.authenticated:
            raise AuthenticationError(response.data.reason)
        if self.config.auto_resubscribe and self._event_subscriptions:
            for subscription_request in self._event_subscriptions.values():
                await self.send_request(subscription_request, EventSubscriptionResponse)
        return True

    async def send_request(
        self,
        request: VTSRequestEnvelope[Any],
        response_model: type[ResponseT],
    ) -> ResponseT:
        """发送请求并解析响应。"""

        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        async with self._lock:
            connection = self._connection
            if connection is None:
                raise VTubeStudioConnectionError("尚未建立到 VTube Studio 的连接")

            payload = json.dumps(request.to_payload(), ensure_ascii=False)
            self._pending_requests[request.request_id] = future
            try:
                await connection.send(payload)
            except ConnectionClosed as exc:
                self._pending_requests.pop(request.request_id, None)
                self._connection = None
                raise VTubeStudioConnectionError("VTube Studio 连接已关闭") from exc
            except WebSocketException as exc:
                self._pending_requests.pop(request.request_id, None)
                raise ResponseError("发送或接收 VTube Studio 消息失败") from exc

        try:
            raw_response = await asyncio.wait_for(
                future,
                timeout=self.config.request_timeout,
            )
        except TimeoutError as exc:
            self._pending_requests.pop(request.request_id, None)
            raise ResponseError(f"等待 {request.message_type} 响应超时") from exc

        return self._parse_response(raw_response, request.request_id, response_model)

    async def _reader_loop(self) -> None:
        """后台读取所有消息，并按 requestID 或事件类型路由。"""

        connection = self._connection
        if connection is None:
            return

        try:
            async for raw_message in connection:
                if not isinstance(raw_message, str):
                    continue
                await self._route_message(raw_message)
        except asyncio.CancelledError:
            raise
        except ConnectionClosed:
            self._connection = None
        except WebSocketException as exc:
            self._connection = None
            self._fail_pending_requests(ResponseError("后台接收 VTube Studio 消息失败"))
            raise VTubeStudioConnectionError("后台接收 VTube Studio 消息失败") from exc
        except EventDispatchError:
            pass
        finally:
            self._fail_pending_requests(
                VTubeStudioConnectionError("VTube Studio 连接已关闭"),
            )

    async def _route_message(self, raw_message: str) -> None:
        """路由收到的文本消息。"""

        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return

        request_id = payload.get("requestID")
        if isinstance(request_id, str) and request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_result(raw_message)
            return

        message_type = payload.get("messageType")
        if not isinstance(message_type, str):
            return
        await self._dispatch_event(message_type, raw_message)

    async def _dispatch_event(self, message_type: str, raw_message: str) -> None:
        """分发事件到已注册监听器。"""

        handlers = self._event_handlers.get(message_type, [])
        if not handlers:
            return

        try:
            envelope = VTSEventEnvelope.model_validate_json(raw_message)
        except ValidationError as exc:
            raise EventDispatchError(f"无法解析事件 {message_type}") from exc

        for handler in list(handlers):
            result = handler(envelope)
            if asyncio.iscoroutine(result):
                await cast(Awaitable[None], result)

    def _fail_pending_requests(self, error: Exception) -> None:
        """使所有挂起请求失败。"""

        pending_requests = list(self._pending_requests.values())
        self._pending_requests.clear()
        for future in pending_requests:
            if not future.done():
                future.set_exception(error)

    def _parse_response(
        self,
        raw_response: Any,
        request_id: str,
        response_model: type[ResponseT],
    ) -> ResponseT:
        """解析 JSON 响应并处理 APIError。"""

        if not isinstance(raw_response, str):
            raise ResponseError("收到的响应不是文本消息")

        try:
            payload = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise ResponseError("响应不是有效 JSON") from exc

        message_type = payload.get("messageType")
        response_request_id = payload.get("requestID")
        if response_request_id != request_id:
            raise ResponseError(
                f"响应 requestID 不匹配，期望 {request_id}，实际 {response_request_id}",
            )

        if message_type == "APIError":
            try:
                error_response = VTSAPIErrorEnvelope.model_validate(payload)
            except ValidationError as exc:
                raise ResponseError("APIError 响应格式无效") from exc
            raise APIError(
                error_id=error_response.data.error_id,
                message=error_response.data.message,
                payload=payload,
            )

        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            raise ResponseError(f"响应无法解析为 {response_model.__name__}") from exc

    def add_event_handler(self, event_name: str, handler: EventHandler) -> None:
        """注册事件回调。"""

        self._event_handlers.setdefault(event_name, []).append(handler)

    def remove_event_handler(self, event_name: str, handler: EventHandler) -> None:
        """移除事件回调。"""

        handlers = self._event_handlers.get(event_name)
        if handlers is None:
            return
        with contextlib.suppress(ValueError):
            handlers.remove(handler)
        if not handlers:
            self._event_handlers.pop(event_name, None)

    def has_event_handlers(self, event_name: str) -> bool:
        """返回指定事件当前是否仍有本地处理器。"""

        return bool(self._event_handlers.get(event_name))

    async def request_permission(
        self,
        request: PermissionRequest,
    ) -> PermissionResponse:
        """请求或查询插件权限。"""

        return await self.send_request(request, PermissionResponse)

    async def subscribe_event(
        self,
        request: EventSubscriptionRequest,
    ) -> EventSubscriptionResponse:
        """订阅事件。"""

        response = await self.send_request(request, EventSubscriptionResponse)
        event_name = request.data.event_name
        if request.data.subscribe and event_name:
            self._event_subscriptions[event_name] = request
        elif event_name:
            self._event_subscriptions.pop(event_name, None)
        else:
            self._event_subscriptions.clear()
        return response

    async def unsubscribe_event(
        self,
        event_name: str | None = None,
    ) -> EventSubscriptionResponse:
        """退订指定事件或全部事件。"""

        request = EventSubscriptionRequest(
            data=EventSubscriptionRequestData(
                eventName=event_name,
                subscribe=False,
                config=EventSubscriptionConfig(),
            ),
        )
        return await self.subscribe_event(request)

    async def get_api_state(self) -> APIStateResponse:
        return await self.send_request(APIStateRequest(), APIStateResponse)

    async def get_statistics(self) -> StatisticsResponse:
        return await self.send_request(StatisticsRequest(), StatisticsResponse)

    async def get_permissions(self) -> PermissionResponse:
        return await self.request_permission(PermissionRequest())

    async def get_folder_info(self) -> VTSFolderInfoResponse:
        return await self.send_request(VTSFolderInfoRequest(), VTSFolderInfoResponse)

    async def get_current_model(self) -> CurrentModelResponse:
        return await self.send_request(CurrentModelRequest(), CurrentModelResponse)

    async def get_available_models(self) -> AvailableModelsResponse:
        return await self.send_request(
            AvailableModelsRequest(),
            AvailableModelsResponse,
        )

    async def load_model(self, request: ModelLoadRequest) -> ModelLoadResponse:
        return await self.send_request(request, ModelLoadResponse)

    async def move_model(self, request: MoveModelRequest) -> MoveModelResponse:
        return await self.send_request(request, MoveModelResponse)

    async def get_hotkeys(
        self,
        request: HotkeysInCurrentModelRequest,
    ) -> HotkeysInCurrentModelResponse:
        return await self.send_request(request, HotkeysInCurrentModelResponse)

    async def trigger_hotkey(
        self,
        request: HotkeyTriggerRequest,
    ) -> HotkeyTriggerResponse:
        return await self.send_request(request, HotkeyTriggerResponse)

    async def get_expression_state(
        self,
        request: ExpressionStateRequest,
    ) -> ExpressionStateResponse:
        return await self.send_request(request, ExpressionStateResponse)

    async def set_expression_active(
        self,
        request: ExpressionActivationRequest,
    ) -> ExpressionActivationResponse:
        return await self.send_request(request, ExpressionActivationResponse)

    async def get_art_meshes(self) -> ArtMeshListResponse:
        return await self.send_request(ArtMeshListRequest(), ArtMeshListResponse)

    async def tint_art_meshes(self, request: ColorTintRequest) -> ColorTintResponse:
        return await self.send_request(request, ColorTintResponse)

    async def get_scene_color_overlay_info(self) -> SceneColorOverlayInfoResponse:
        return await self.send_request(
            SceneColorOverlayInfoRequest(),
            SceneColorOverlayInfoResponse,
        )

    async def is_face_found(self) -> FaceFoundResponse:
        return await self.send_request(FaceFoundRequest(), FaceFoundResponse)

    async def get_input_parameters(self) -> InputParameterListResponse:
        return await self.send_request(
            InputParameterListRequest(),
            InputParameterListResponse,
        )

    async def get_parameter_value(
        self,
        request: ParameterValueRequest,
    ) -> ParameterValueResponse:
        return await self.send_request(request, ParameterValueResponse)

    async def get_live2d_parameters(self) -> Live2DParameterListResponse:
        return await self.send_request(
            Live2DParameterListRequest(),
            Live2DParameterListResponse,
        )

    async def create_parameter(
        self,
        request: ParameterCreationRequest,
    ) -> ParameterCreationResponse:
        return await self.send_request(request, ParameterCreationResponse)

    async def delete_parameter(
        self,
        request: ParameterDeletionRequest,
    ) -> ParameterDeletionResponse:
        return await self.send_request(request, ParameterDeletionResponse)

    async def inject_parameter_data(
        self,
        request: InjectParameterDataRequest,
    ) -> InjectParameterDataResponse:
        return await self.send_request(request, InjectParameterDataResponse)

    async def get_current_model_physics(self) -> GetCurrentModelPhysicsResponse:
        return await self.send_request(
            GetCurrentModelPhysicsRequest(),
            GetCurrentModelPhysicsResponse,
        )

    async def set_current_model_physics(
        self,
        request: SetCurrentModelPhysicsRequest,
    ) -> SetCurrentModelPhysicsResponse:
        return await self.send_request(request, SetCurrentModelPhysicsResponse)

    async def get_ndi_config(self, request: NDIConfigRequest) -> NDIConfigResponse:
        return await self.send_request(request, NDIConfigResponse)

    async def get_items(self, request: ItemListRequest) -> ItemListResponse:
        return await self.send_request(request, ItemListResponse)

    async def load_item(self, request: ItemLoadRequest) -> ItemLoadResponse:
        return await self.send_request(request, ItemLoadResponse)

    async def unload_item(self, request: ItemUnloadRequest) -> ItemUnloadResponse:
        return await self.send_request(request, ItemUnloadResponse)

    async def control_item_animation(
        self,
        request: ItemAnimationControlRequest,
    ) -> ItemAnimationControlResponse:
        return await self.send_request(request, ItemAnimationControlResponse)

    async def move_items(self, request: ItemMoveRequest) -> ItemMoveResponse:
        return await self.send_request(request, ItemMoveResponse)

    async def sort_item(self, request: ItemSortRequest) -> ItemSortResponse:
        return await self.send_request(request, ItemSortResponse)

    async def select_art_meshes(
        self,
        request: ArtMeshSelectionRequest,
    ) -> ArtMeshSelectionResponse:
        return await self.send_request(request, ArtMeshSelectionResponse)

    async def pin_item(self, request: ItemPinRequest) -> ItemPinResponse:
        return await self.send_request(request, ItemPinResponse)

    async def get_post_processing(
        self,
        request: PostProcessingListRequest,
    ) -> PostProcessingListResponse:
        return await self.send_request(request, PostProcessingListResponse)

    async def update_post_processing(
        self,
        request: PostProcessingUpdateRequest,
    ) -> PostProcessingUpdateResponse:
        return await self.send_request(request, PostProcessingUpdateResponse)

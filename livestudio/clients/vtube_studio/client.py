"""Async WebSocket client for the VTube Studio public API."""

from __future__ import annotations

import asyncio
import json
from typing import Any, TypeVar

from pydantic import ValidationError
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from .config import VTubeStudioConfig, VTubeStudioPluginInfo
from .errors import (
    APIError,
    AuthenticationError,
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
    VTSFolderInfoRequest,
    VTSFolderInfoResponse,
    VTSRequestEnvelope,
    VTSResponseEnvelope,
)

ResponseT = TypeVar("ResponseT", bound=VTSResponseEnvelope[Any])


class VTubeStudioClient:
    """基于 WebSocket 的异步 VTube Studio API 客户端。"""

    def __init__(self, config: VTubeStudioConfig, plugin_info: VTubeStudioPluginInfo) -> None:
        self.config = config
        self.plugin_info = plugin_info
        self._connection: ClientConnection | None = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """当前是否已建立 WebSocket 连接。"""

        return self._connection is not None

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
        except (OSError, TimeoutError, WebSocketException) as exc:
            self._connection = None
            raise VTubeStudioConnectionError(f"无法连接到 {self.config.websocket_url}") from exc

    async def disconnect(self) -> None:
        """关闭 WebSocket 连接。"""

        connection = self._connection
        self._connection = None
        if connection is None:
            return

        try:
            await connection.close()
        except WebSocketException as exc:
            raise VTubeStudioConnectionError("关闭 VTube Studio 连接失败") from exc

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
        return True

    async def send_request(self, request: VTSRequestEnvelope[Any], response_model: type[ResponseT]) -> ResponseT:
        """发送请求并解析响应。"""

        async with self._lock:
            connection = self._connection
            if connection is None:
                raise VTubeStudioConnectionError("尚未建立到 VTube Studio 的连接")

            payload = json.dumps(request.to_payload(), ensure_ascii=False)
            try:
                await connection.send(payload)
                raw_response = await asyncio.wait_for(connection.recv(), timeout=self.config.request_timeout)
            except TimeoutError as exc:
                raise ResponseError(f"等待 {request.message_type} 响应超时") from exc
            except ConnectionClosed as exc:
                self._connection = None
                raise VTubeStudioConnectionError("VTube Studio 连接已关闭") from exc
            except WebSocketException as exc:
                raise ResponseError("发送或接收 VTube Studio 消息失败") from exc

        return self._parse_response(raw_response, request.request_id, response_model)

    def _parse_response(self, raw_response: Any, request_id: str, response_model: type[ResponseT]) -> ResponseT:
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

    async def get_api_state(self) -> APIStateResponse:
        return await self.send_request(APIStateRequest(), APIStateResponse)

    async def get_statistics(self) -> StatisticsResponse:
        return await self.send_request(StatisticsRequest(), StatisticsResponse)

    async def get_folder_info(self) -> VTSFolderInfoResponse:
        return await self.send_request(VTSFolderInfoRequest(), VTSFolderInfoResponse)

    async def get_current_model(self) -> CurrentModelResponse:
        return await self.send_request(CurrentModelRequest(), CurrentModelResponse)

    async def get_available_models(self) -> AvailableModelsResponse:
        return await self.send_request(AvailableModelsRequest(), AvailableModelsResponse)

    async def load_model(self, request: ModelLoadRequest) -> ModelLoadResponse:
        return await self.send_request(request, ModelLoadResponse)

    async def move_model(self, request: MoveModelRequest) -> MoveModelResponse:
        return await self.send_request(request, MoveModelResponse)

    async def get_hotkeys(self, request: HotkeysInCurrentModelRequest) -> HotkeysInCurrentModelResponse:
        return await self.send_request(request, HotkeysInCurrentModelResponse)

    async def trigger_hotkey(self, request: HotkeyTriggerRequest) -> HotkeyTriggerResponse:
        return await self.send_request(request, HotkeyTriggerResponse)

    async def get_expression_state(self, request: ExpressionStateRequest) -> ExpressionStateResponse:
        return await self.send_request(request, ExpressionStateResponse)

    async def set_expression_active(self, request: ExpressionActivationRequest) -> ExpressionActivationResponse:
        return await self.send_request(request, ExpressionActivationResponse)

    async def get_art_meshes(self) -> ArtMeshListResponse:
        return await self.send_request(ArtMeshListRequest(), ArtMeshListResponse)

    async def tint_art_meshes(self, request: ColorTintRequest) -> ColorTintResponse:
        return await self.send_request(request, ColorTintResponse)

    async def get_scene_color_overlay_info(self) -> SceneColorOverlayInfoResponse:
        return await self.send_request(SceneColorOverlayInfoRequest(), SceneColorOverlayInfoResponse)

    async def is_face_found(self) -> FaceFoundResponse:
        return await self.send_request(FaceFoundRequest(), FaceFoundResponse)

    async def get_input_parameters(self) -> InputParameterListResponse:
        return await self.send_request(InputParameterListRequest(), InputParameterListResponse)

    async def get_parameter_value(self, request: ParameterValueRequest) -> ParameterValueResponse:
        return await self.send_request(request, ParameterValueResponse)

    async def get_live2d_parameters(self) -> Live2DParameterListResponse:
        return await self.send_request(Live2DParameterListRequest(), Live2DParameterListResponse)

    async def create_parameter(self, request: ParameterCreationRequest) -> ParameterCreationResponse:
        return await self.send_request(request, ParameterCreationResponse)

    async def delete_parameter(self, request: ParameterDeletionRequest) -> ParameterDeletionResponse:
        return await self.send_request(request, ParameterDeletionResponse)

    async def inject_parameter_data(self, request: InjectParameterDataRequest) -> InjectParameterDataResponse:
        return await self.send_request(request, InjectParameterDataResponse)

    async def get_current_model_physics(self) -> GetCurrentModelPhysicsResponse:
        return await self.send_request(GetCurrentModelPhysicsRequest(), GetCurrentModelPhysicsResponse)

    async def set_current_model_physics(self, request: SetCurrentModelPhysicsRequest) -> SetCurrentModelPhysicsResponse:
        return await self.send_request(request, SetCurrentModelPhysicsResponse)

    async def get_ndi_config(self, request: NDIConfigRequest) -> NDIConfigResponse:
        return await self.send_request(request, NDIConfigResponse)

    async def get_items(self, request: ItemListRequest) -> ItemListResponse:
        return await self.send_request(request, ItemListResponse)

    async def load_item(self, request: ItemLoadRequest) -> ItemLoadResponse:
        return await self.send_request(request, ItemLoadResponse)

    async def unload_item(self, request: ItemUnloadRequest) -> ItemUnloadResponse:
        return await self.send_request(request, ItemUnloadResponse)

    async def control_item_animation(self, request: ItemAnimationControlRequest) -> ItemAnimationControlResponse:
        return await self.send_request(request, ItemAnimationControlResponse)

    async def move_items(self, request: ItemMoveRequest) -> ItemMoveResponse:
        return await self.send_request(request, ItemMoveResponse)

    async def sort_item(self, request: ItemSortRequest) -> ItemSortResponse:
        return await self.send_request(request, ItemSortResponse)

    async def select_art_meshes(self, request: ArtMeshSelectionRequest) -> ArtMeshSelectionResponse:
        return await self.send_request(request, ArtMeshSelectionResponse)

    async def pin_item(self, request: ItemPinRequest) -> ItemPinResponse:
        return await self.send_request(request, ItemPinResponse)

    async def get_post_processing(self, request: PostProcessingListRequest) -> PostProcessingListResponse:
        return await self.send_request(request, PostProcessingListResponse)

    async def update_post_processing(self, request: PostProcessingUpdateRequest) -> PostProcessingUpdateResponse:
        return await self.send_request(request, PostProcessingUpdateResponse)

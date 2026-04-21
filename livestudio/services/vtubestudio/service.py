"""VTube Studio 服务。"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable
from pathlib import Path

from livestudio.config import ConfigManager
from livestudio.log import logger
from livestudio.tween import ControlledParameterState, ParameterTweenEngine, TweenMode

from ...clients.vtube_studio.client import VTubeStudioClient
from ...clients.vtube_studio.config import VTubeStudioConfig
from ...clients.vtube_studio.discovery import VTubeStudioDiscovery
from ...clients.vtube_studio.errors import APIError, AuthenticationError
from ...clients.vtube_studio.event_manager import ListenerHandler, VTSEventManager
from ...clients.vtube_studio.models import (
    EventName,
    EventSubscriptionConfig,
    EventSubscriptionRequest,
    EventSubscriptionRequestData,
    EventSubscriptionResponse,
    InjectParameterDataRequest,
    InjectParameterDataRequestData,
    InjectParameterValue,
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
        from .model_expression_sync import ModelExpressionSyncService

        self.config_manager = config_manager or ConfigManager(
            VTubeStudioConfig,
            Path(config_path) if config_path is not None else Path("config") / "vtube_studio.yaml",
        )
        self._client: VTubeStudioClient | None = None
        self._events: VTSEventManager | None = None
        self._discovery: VTubeStudioDiscovery | None = None
        self._model_expression_sync_service: ModelExpressionSyncService = ModelExpressionSyncService(self)
        self._subservices: tuple[ModelExpressionSyncService, ...] = (self._model_expression_sync_service,)
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

        for subservice in reversed(self._subservices):
            await subservice.close()
        await self.tween.close()
        await self.config_manager.save()
        client = self._client
        self._client = None
        self._events = None
        self._discovery = None
        if client is not None:
            await client.disconnect()

    async def start(self) -> None:
        """启动连接、认证和模型表情自动同步。"""

        authenticated = await self._authenticate_session(allow_request_token=True)

        if not authenticated:
            raise RuntimeError("VTube Studio 认证失败")

        for subservice in self._subservices:
            await subservice.start()

    async def connect_and_authenticate(self, authentication_token: str | None = None) -> bool:
        """连接到 VTube Studio 并执行认证流程。"""

        try:
            return await self._authenticate_session(authentication_token=authentication_token)
        except Exception:
            logger.exception("连接并认证失败")
            with contextlib.suppress(Exception):
                await self._require_client().disconnect()
            return False

    async def reconnect(self, authentication_token: str) -> bool:
        """重新建立连接并进行认证。"""

        try:
            return await self._authenticate_session(authentication_token=authentication_token, disconnect_first=True)
        except Exception:
            logger.exception("重连并认证失败")
            with contextlib.suppress(Exception):
                await self._require_client().disconnect()
            return False

    async def _authenticate_session(
        self,
        authentication_token: str | None = None,
        *,
        allow_request_token: bool = False,
        disconnect_first: bool = False,
    ) -> bool:
        """统一处理连接、申请 token 与认证流程。"""

        client = self._require_client()

        if disconnect_first:
            with contextlib.suppress(Exception):
                await client.disconnect()

        await client.connect()

        token = authentication_token or self.config.authentication_token
        if token is None:
            if not allow_request_token:
                logger.error("未提供 authentication_token，无法完成会话认证")
                return False
            token = await self._request_token(store=True)

        try:
            return await client.authenticate(token)
        except AuthenticationError:
            if not allow_request_token:
                raise
            logger.warning("[WARN] 认证令牌无效或已被撤销，正在重新获取 token")
            token = await self._request_token(store=True)
            return await client.authenticate(token)

    async def _request_token(self, *, store: bool = False) -> str:
        """申请认证令牌，并按需持久化。"""

        try:
            authentication_token = await self._require_client().request_token()
        except APIError as exc:
            if exc.error_id == 50:
                raise RuntimeError("用户已拒绝插件认证请求，请在 VTube Studio 中允许后重试") from exc
            raise

        if store:
            self.config.authentication_token = authentication_token
            await self.config_manager.save()

        return authentication_token

    async def subscribe(
        self,
        event_name: EventName | str,
        handler: ListenerHandler | None = None,
        *,
        config: EventSubscriptionConfig | None = None,
    ) -> EventSubscriptionResponse:
        if handler is not None:
            self._require_events().add_handler(event_name, handler)

        request = EventSubscriptionRequest(
            data=EventSubscriptionRequestData(
                eventName=event_name,
                subscribe=True,
                config=config or EventSubscriptionConfig(),
            ),
        )

        try:
            return await self._require_client().subscribe_event(request)
        except Exception:
            if handler is not None:
                self._require_events().remove_handler(event_name, handler)
            raise

    async def unsubscribe(
        self,
        event_name: EventName | str,
        handler: ListenerHandler | None = None,
    ) -> EventSubscriptionResponse:
        if handler is not None:
            self._require_events().remove_handler(event_name, handler)
        return await self._require_client().unsubscribe_event(event_name)

    async def listen_for_api(
        self,
        timeout: float | None = None,
        max_messages: int | None = None,
    ) -> list[VTubeStudioAPIStateBroadcast]:
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
        await self._require_client().inject_parameter_data(request)
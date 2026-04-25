"""VTube Studio 服务。"""

from __future__ import annotations

import contextlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from livestudio.config import ConfigManager
from livestudio.log import logger
from livestudio.services.audio_stream.base import AudioStreamSource
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
    ) -> None:
        self.config_manager = ConfigManager(
            VTubeStudioConfig,
            Path("config") / "vtube_studio.yaml",
        )
        self._client: VTubeStudioClient | None = None
        self._events: VTSEventManager | None = None
        self._discovery: VTubeStudioDiscovery | None = None
        self.tween = ParameterTweenEngine(
            self._send_parameter_states,
        )

    @property
    def config(self) -> VTubeStudioConfig:
        """返回最新配置快照。"""

        return self.config_manager.config

    @property
    def client(self) -> VTubeStudioClient:
        """返回已初始化的底层客户端。"""
        if self._client is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return self._client

    @property
    def events(self) -> VTSEventManager:
        """返回已初始化的事件管理器。"""
        if self._events is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return self._events

    @property
    def discovery(self) -> VTubeStudioDiscovery:
        """返回已初始化的 discovery 实例。"""
        if self._discovery is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return self._discovery

    async def initialize(self) -> None:
        """加载配置并创建内部依赖。"""

        await self.config_manager.load()
        self._client = VTubeStudioClient(
            config=self.config,
            plugin_info=self.config.plugin,
        )
        self._events = VTSEventManager(self._client, self.config.event_queue_size)
        self._discovery = VTubeStudioDiscovery(self.config)

    async def close(self) -> None:
        """释放该服务持有的后台资源。"""

        await self.tween.close()
        await self.client.disconnect()
        await self.config_manager.save()
        self._client = None
        self._events = None
        self._discovery = None

    async def start(self) -> None:
        """启动连接、认证流程与子服务。"""

        authenticated = await self._authenticate_session(allow_request_token=True)
        self.tween.start()
        if not authenticated:
            raise RuntimeError("VTube Studio 认证失败")

    async def connect_and_authenticate(
        self,
        authentication_token: str | None = None,
    ) -> bool:
        """连接到 VTube Studio 并执行认证流程。"""

        try:
            return await self._authenticate_session(
                authentication_token=authentication_token,
            )
        except Exception:
            logger.exception("连接并认证失败")
            with contextlib.suppress(Exception):
                await self.client.disconnect()
            return False

    async def reconnect(self, authentication_token: str) -> bool:
        """重新建立连接并进行认证。"""

        try:
            return await self._authenticate_session(
                authentication_token=authentication_token,
                disconnect_first=True,
            )
        except Exception:
            logger.exception("重连并认证失败")
            with contextlib.suppress(Exception):
                await self.client.disconnect()
            return False

    async def _authenticate_session(
        self,
        authentication_token: str | None = None,
        *,
        allow_request_token: bool = False,
        disconnect_first: bool = False,
    ) -> bool:
        """统一处理连接、申请 token 与认证流程。"""

        if disconnect_first:
            with contextlib.suppress(Exception):
                await self.client.disconnect()

        await self.client.connect()

        token = authentication_token or self.config.authentication_token
        if token is None:
            if not allow_request_token:
                logger.error("未提供 authentication_token，无法完成会话认证")
                return False
            token = await self._request_token(store=True)

        try:
            return await self.client.authenticate(token)
        except AuthenticationError:
            if not allow_request_token:
                raise
            logger.warning("[WARN] 认证令牌无效或已被撤销，正在重新获取 token")
            token = await self._request_token(store=True)
            return await self.client.authenticate(token)

    async def _request_token(self, *, store: bool = False) -> str:
        """申请认证令牌，并按需持久化。"""

        try:
            authentication_token = await self.client.request_token()
        except APIError as exc:
            if exc.error_id == 50:
                raise RuntimeError(
                    "用户已拒绝插件认证请求，请在 VTube Studio 中允许后重试",
                ) from exc
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
            self.events.add_handler(event_name, handler)

        request = EventSubscriptionRequest(
            data=EventSubscriptionRequestData(
                eventName=event_name,
                subscribe=True,
                config=config or EventSubscriptionConfig(),
            ),
        )

        try:
            return await self.events.subscribe(request)
        except Exception:
            if handler is not None:
                self.events.remove_handler(event_name, handler)
            raise

    async def unsubscribe(
        self,
        event_name: EventName | str,
        handler: ListenerHandler | None = None,
    ) -> EventSubscriptionResponse | None:
        if handler is not None:
            self.events.remove_handler(event_name, handler)

        if handler is not None and self.events.has_handlers(event_name):
            return None

        try:
            return await self.events.unsubscribe(event_name)
        except Exception:
            if handler is not None:
                self.events.add_handler(event_name, handler)
            raise

    async def listen_for_api(
        self,
        timeout: float | None = None,
        max_messages: int | None = None,
    ) -> list[VTubeStudioAPIStateBroadcast]:
        broadcasts: list[VTubeStudioAPIStateBroadcast] = []
        async for broadcast in self.discovery.listen(
            timeout=timeout,
            max_messages=max_messages,
        ):
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
                parameterValues=[
                    InjectParameterValue(id=state.name, value=state.value)
                    for state in parameter_states
                ],
            ),
        )
        await self.client.inject_parameter_data(request)

"""VTube Studio 服务。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from livestudio.config import ConfigManager
from livestudio.log import logger
from livestudio.tween import ControlledParameterState, ParameterTweenEngine

from ....clients.vtube_studio.client import VTubeStudioClient
from ....clients.vtube_studio.config import VTubeStudioConfig
from ....clients.vtube_studio.discovery import VTubeStudioDiscovery
from ....clients.vtube_studio.errors import APIError, AuthenticationError
from ....clients.vtube_studio.event_manager import ListenerHandler, VTSEventManager
from ....clients.vtube_studio.models import (
    EventName,
    EventSubscriptionConfig,
    EventSubscriptionRequest,
    EventSubscriptionRequestData,
    EventSubscriptionResponse,
    InjectParameterDataRequest,
    InjectParameterDataRequestData,
    InjectParameterValue,
    VTSEventEnvelope,
    VTubeStudioAPIStateBroadcast,
)
from ..base import PlatformService
from ..model import PlatformModelIdentity
from .config import VTubeStudioModelConfig


class VTubeStudio(PlatformService):
    """对外暴露稳定业务接口的服务层。"""

    platform_name = "vtubestudio"

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
        self._model_config_manager: ConfigManager[VTubeStudioModelConfig] | None = None
        self._current_model: PlatformModelIdentity | None = None
        self._tween = ParameterTweenEngine(
            self._send_parameter_states,
        )
        self._initialized = False
        self._started = False

    @property
    def name(self) -> str:
        """平台唯一名称。"""

        return self.platform_name

    @property
    def tween(self) -> ParameterTweenEngine:
        """返回 VTube Studio 参数缓动引擎。"""

        return self._tween

    @property
    def config(self) -> VTubeStudioConfig:
        """返回最新配置快照。"""

        return self.config_manager.config

    @property
    def model_config(self) -> VTubeStudioModelConfig:
        """返回当前模型配置快照。"""

        if self._model_config_manager is None:
            raise RuntimeError("当前没有已加载的模型配置")
        return self._model_config_manager.config

    @property
    def model_config_manager(self) -> ConfigManager[VTubeStudioModelConfig]:
        """返回当前模型配置管理器实例。"""

        if self._model_config_manager is None:
            raise RuntimeError("当前没有已加载的模型配置")
        return self._model_config_manager

    @property
    def current_model(self) -> PlatformModelIdentity:
        """返回当前平台已加载模型身份。"""
        if self._current_model is None:
            raise RuntimeError("当前没有已加载的模型")
        return self._current_model

    @property
    def is_initialized(self) -> bool:
        """服务是否已初始化。"""

        return self._initialized

    @property
    def is_started(self) -> bool:
        """服务是否已启动。"""

        return self._started

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

        if self._initialized:
            return
        await self.config_manager.load()
        self._client = VTubeStudioClient(
            config=self.config,
            plugin_info=self.config.plugin,
        )
        self._events = VTSEventManager(self._client, self.config.event_queue_size)
        self._discovery = VTubeStudioDiscovery(self.config)
        self._initialized = True

    async def stop(self) -> None:
        """释放该服务持有的后台资源。"""

        await self._stop(save_config=True)

    async def _stop(self, *, save_config: bool) -> None:
        """停止服务并按需保存配置。"""

        if not self._initialized:
            return
        await self.tween.stop()
        if self._client is not None:
            await self._client.disconnect()
        if save_config:
            await self.config_manager.save()
        self._client = None
        self._events = None
        self._discovery = None
        self._model_config_manager = None
        self._current_model = None
        self._initialized = False
        self._started = False

    async def start(self) -> None:
        """启动连接与认证流程。"""

        if self._started:
            return
        if not self._initialized:
            await self.initialize()
        await self.connect()
        await self.authenticate()
        self.tween.start()
        self._started = True

    async def restart(self) -> None:
        """重启 VTube Studio 服务并重新加载配置。"""

        await self._stop(save_config=False)
        await self.initialize()
        await self.start()

    async def reload_model_config(
        self,
        model_id: str,
        model_name: str,
    ) -> VTubeStudioModelConfig:
        """按当前 VTube Studio 模型重建并加载模型级配置。"""

        identity = PlatformModelIdentity(
            platform_name=self.platform_name,
            model_id=model_id,
            model_name=model_name,
        )
        config_path = self._build_model_config_path(identity)
        model_config_manager = ConfigManager(VTubeStudioModelConfig, config_path)
        model_config = await model_config_manager.reload()
        model_config.model.id = model_id
        model_config.model.name = model_name
        await model_config_manager.save()
        self._model_config_manager = model_config_manager
        self._current_model = identity
        logger.info(
            "已加载 VTube Studio 模型配置: {} ({}) -> {}",
            model_name,
            model_id,
            config_path,
        )
        return model_config

    def _build_model_config_path(self, identity: PlatformModelIdentity) -> Path:
        safe_name = self._sanitize_model_config_part(identity.model_name)
        safe_id = self._sanitize_model_config_part(identity.model_id)
        filename = f"{safe_name}_{safe_id}.yaml"
        return Path(self.config.model_config_dir) / filename

    def _sanitize_model_config_part(self, value: str) -> str:
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
        return sanitized or "unknown"

    async def connect(self) -> None:
        """连接到 VTube Studio。"""

        await self.client.connect()

    async def authenticate(
        self,
    ) -> None:
        """使用给定令牌或配置中的令牌完成认证。"""

        token = self.config.authentication_token
        if token is None:
            logger.warning("[WARN] 当前没有认证令牌，正在申请新的 token")
            token = await self.request_token()
            logger.success("[SUCCESS] 已获取新的认证令牌")
        try:
            await self.client.authenticate(token)
        except AuthenticationError:
            logger.warning("[WARN] 认证令牌无效或已被撤销，正在重新获取 token")
            token = await self.request_token()
            await self.client.authenticate(token)
            logger.success("[SUCCESS] 已获取新的认证令牌并完成认证")

    async def request_token(self) -> str:
        """申请认证令牌，并按需持久化。"""

        try:
            authentication_token = await self.client.request_token()
        except APIError as exc:
            if exc.error_id == 50:
                raise RuntimeError(
                    "用户已拒绝插件认证请求，请在 VTube Studio 中允许后重试",
                ) from exc
            raise

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
        mode: Literal["set", "add"] = "set",
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

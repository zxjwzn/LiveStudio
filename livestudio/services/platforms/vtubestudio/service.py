"""VTube Studio 服务"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from livestudio.config import ConfigManager
from livestudio.services.platforms.model_config_service import (
    PlatformModelConfigService,
)
from livestudio.services.semantic_actions import (
    SemanticActionAdapter,
    SemanticActionState,
)
from livestudio.tween import ControlledParameterState, ParameterTweenEngine
from livestudio.utils.log import logger
from livestudio.utils.paths import config_path

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
    ParameterValueRequest,
    ParameterValueRequestData,
    VTubeStudioAPIStateBroadcast,
)
from ..base import PlatformService
from ..model import PlatformModelIdentity
from .config import VTubeStudioModelConfig
from .semantic import (
    VTubeStudioSemanticAdapter,
    default_vtube_studio_parameter_specs,
    default_vtube_studio_semantic_bindings,
)


class VTubeStudio(PlatformService):
    """对外暴露稳定业务接口的服务层"""

    platform_name = "vtubestudio"

    def __init__(
        self,
    ) -> None:
        self.config_manager = ConfigManager(
            VTubeStudioConfig,
            config_path("vtube_studio.yaml"),
        )
        self._client: VTubeStudioClient | None = None
        self._events: VTSEventManager | None = None
        self._discovery: VTubeStudioDiscovery | None = None
        self._model_config_service: (
            PlatformModelConfigService[VTubeStudioModelConfig] | None
        ) = None
        self._semantic_adapter: VTubeStudioSemanticAdapter | None = None
        self._tween = ParameterTweenEngine(
            self.send_parameter_states,
        )
        self._initialized = False
        self._started = False

    @property
    def name(self) -> str:
        """平台唯一名称"""

        return self.platform_name

    @property
    def tween(self) -> ParameterTweenEngine:
        """返回 VTube Studio 参数缓动引擎"""

        return self._tween

    @property
    def semantic_adapter(self) -> SemanticActionAdapter | None:
        """返回当前模型的 VTube Studio 语义动作适配器"""

        return self._semantic_adapter

    @property
    def config(self) -> VTubeStudioConfig:
        """返回最新配置快照"""

        return self.config_manager.config

    @property
    def model_config(self) -> VTubeStudioModelConfig:
        """返回当前模型配置快照"""

        if (
            self._model_config_service is None
            or self._model_config_service.config is None
        ):
            raise RuntimeError("当前没有已加载的模型配置")
        return self._model_config_service.config

    @property
    def model_config_manager(self) -> ConfigManager[VTubeStudioModelConfig]:
        """返回当前模型配置管理器实例"""

        if (
            self._model_config_service is None
            or self._model_config_service.manager is None
        ):
            raise RuntimeError("当前没有已加载的模型配置")
        return self._model_config_service.manager

    @property
    def current_model(self) -> PlatformModelIdentity:
        """返回当前平台已加载模型身份"""
        if (
            self._model_config_service is None
            or self._model_config_service.identity is None
        ):
            raise RuntimeError("当前没有已加载的模型")
        return self._model_config_service.identity

    @property
    def is_initialized(self) -> bool:
        """服务是否已初始化"""

        return self._initialized

    @property
    def is_started(self) -> bool:
        """服务是否已启动"""

        return self._started

    @property
    def client(self) -> VTubeStudioClient:
        """返回已初始化的底层客户端"""
        if self._client is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return self._client

    @property
    def events(self) -> VTSEventManager:
        """返回已初始化的事件管理器"""
        if self._events is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return self._events

    @property
    def discovery(self) -> VTubeStudioDiscovery:
        """返回已经准备好的自动发现对象"""
        if self._discovery is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return self._discovery

    async def initialize(self) -> None:
        """加载配置并创建内部依赖"""

        if self._initialized:
            return
        await self.config_manager.load()
        self._client = VTubeStudioClient(
            config=self.config,
            plugin_info=self.config.plugin,
        )
        self._events = VTSEventManager(self._client, self.config.event_queue_size)
        self._discovery = VTubeStudioDiscovery(self.config)
        self._model_config_service = PlatformModelConfigService(
            config_model=VTubeStudioModelConfig,
            model_config_dir=self.config.model_config_dir,
            default_bindings=default_vtube_studio_semantic_bindings(),
            default_parameter_specs=default_vtube_studio_parameter_specs(),
        )
        self._initialized = True

    async def stop(self) -> None:
        """停止服务并按需保存配置"""

        if not self._initialized:
            return
        await self.tween.stop()
        if self._client is not None:
            await self._client.disconnect()
        await self.config_manager.save()
        if self._model_config_service is not None:
            await self._model_config_service.save()
        self._client = None
        self._events = None
        self._discovery = None
        self._model_config_service = None
        self._semantic_adapter = None
        self._initialized = False
        self._started = False

    async def start(self) -> None:
        """启动连接与认证流程"""

        if self._started:
            return
        if not self._initialized:
            await self.initialize()
        try:
            await self.connect()
            await self.authenticate()
            self.tween.start()
            self._started = True
        except Exception:
            await self.tween.stop()
            if self._client is not None:
                await self._client.disconnect()
            self._started = False
            raise

    async def reload_model_config(
        self,
        model_id: str,
        model_name: str,
    ) -> VTubeStudioModelConfig:
        """按当前 VTube Studio 模型重建并加载模型级配置"""

        identity = PlatformModelIdentity(
            platform_name=self.platform_name,
            model_id=model_id,
            model_name=model_name,
        )
        if self._model_config_service is None:
            self._model_config_service = PlatformModelConfigService(
                config_model=VTubeStudioModelConfig,
                model_config_dir=self.config.model_config_dir,
                default_bindings=default_vtube_studio_semantic_bindings(),
                default_parameter_specs=default_vtube_studio_parameter_specs(),
            )
        model_config = await self._model_config_service.load(identity)
        self._semantic_adapter = VTubeStudioSemanticAdapter(
            model_config.semantic_profile,
            model_config.parameter_specs,
        )
        logger.info(
            "已加载 VTube Studio 模型配置: {} ({}) -> {}",
            model_name,
            model_id,
            self.model_config_manager.path,
        )
        return model_config

    async def connect(self) -> None:
        """连接到 VTube Studio"""

        await self.client.connect()

    async def authenticate(
        self,
    ) -> None:
        """使用给定令牌或配置中的令牌完成认证"""

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
        """申请认证令牌，并按需持久化"""

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
        return [
            broadcast
            async for broadcast in self.discovery.listen(
                timeout=timeout,
                max_messages=max_messages,
            )
        ]

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

    async def get_semantic_value(self, action: str) -> SemanticActionState | None:
        """查询 VTube Studio 真实参数并归一化为语义动作值"""

        adapter = self.semantic_adapter
        if adapter is None:
            return None
        parameter_names = adapter.platform_parameters_for(action)
        if not parameter_names:
            return None

        platform_values: dict[str, float] = {}
        for parameter_name in parameter_names:
            response = await self.client.get_parameter_value(
                ParameterValueRequest(
                    data=ParameterValueRequestData(name=parameter_name),
                ),
            )
            platform_values[parameter_name] = response.data.value

        return adapter.normalize_platform_values(action, platform_values)

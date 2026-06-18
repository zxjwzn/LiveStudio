"""VTube Studio 服务"""

import asyncio
import contextlib
from collections.abc import Iterable
from typing import Literal

from livestudio.clients.vtube_studio.client import EventHandler as ListenerHandler
from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.clients.vtube_studio.config import VTubeStudioConfig
from livestudio.clients.vtube_studio.discovery import VTubeStudioDiscovery
from livestudio.clients.vtube_studio.errors import (
    APIError,
    AuthenticationError,
    VTubeStudioConnectionError,
)
from livestudio.clients.vtube_studio.models import (
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
from livestudio.config import ConfigManager
from livestudio.services.expression.models import NativeExpressionTrigger
from livestudio.services.platforms.base import PlatformService
from livestudio.services.platforms.model import PlatformModelIdentity
from livestudio.services.platforms.model_config_service import (
    PlatformModelConfigService,
)
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticActionAdapter,
)
from livestudio.services.tween import ControlledParameterState, ParameterTweenEngine
from livestudio.utils.log import logger
from livestudio.utils.paths import config_path

from .config import VTubeStudioModelConfig
from .expression_adapter import VTSExpressionAdapter


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
        self._discovery: VTubeStudioDiscovery | None = None
        self._model_config_service: PlatformModelConfigService[VTubeStudioModelConfig] | None = None
        self._semantic_adapter: SemanticActionAdapter | None = None
        self._expression_adapter: VTSExpressionAdapter | None = None
        self._tween = ParameterTweenEngine(
            self.send_parameter_states,
        )

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

        if self._model_config_service is None or self._model_config_service.config is None:
            raise RuntimeError("当前没有已加载的模型配置")
        return self._model_config_service.config

    @property
    def model_config_manager(self) -> ConfigManager[VTubeStudioModelConfig]:
        """返回当前模型配置管理器实例"""

        if self._model_config_service is None or self._model_config_service.manager is None:
            raise RuntimeError("当前没有已加载的模型配置")
        return self._model_config_service.manager

    @property
    def current_model(self) -> PlatformModelIdentity:
        """返回当前平台已加载模型身份"""
        if self._model_config_service is None or self._model_config_service.identity is None:
            raise RuntimeError("当前没有已加载的模型")
        return self._model_config_service.identity

    @property
    def client(self) -> VTubeStudioClient:
        """返回已初始化的底层客户端"""
        if self._client is None:
            raise RuntimeError("VTubeStudio 尚未初始化，请先调用 initialize()")
        return self._client

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
        self._discovery = VTubeStudioDiscovery(self.config)
        self._model_config_service = PlatformModelConfigService(
            config_model=VTubeStudioModelConfig,
            model_config_dir=self.config.model_config_dir,
        )
        self._mark_initialized()

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
        self._discovery = None
        self._model_config_service = None
        self._semantic_adapter = None
        self._expression_adapter = None
        self._mark_stopped(reset_initialized=True)

    async def start(self) -> None:
        """启动连接与认证流程，连接失败时自动重连直到成功"""

        if self._started:
            return
        if not self._initialized:
            await self.initialize()

        retry_delay = 3.0
        max_delay = 30.0
        backoff_factor = 1.5

        while True:
            try:
                await self.connect()
                await self.authenticate()
                self.tween.start()
                self._mark_started()
                logger.success("VTube Studio 已连接并完成认证")
            except VTubeStudioConnectionError as exc:
                logger.warning(f"连接 VTube Studio 失败: {exc}，{retry_delay:.1f}秒后重试...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * backoff_factor, max_delay)
            except Exception:
                await self.tween.stop()
                if self._client is not None:
                    await self._client.disconnect()
                raise
            else:
                return

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
            )
        model_config = await self._model_config_service.load(identity)
        await self._refresh_parameter_specs(model_config)
        self._semantic_adapter = SemanticActionAdapter(
            model_config.semantic_profile,
            parameter_specs=model_config.parameter_specs,
            engine=self.tween,
        )
        self._expression_adapter = VTSExpressionAdapter(
            name_to_file={expression.name: expression.file for expression in model_config.expressions},
        )
        logger.info(
            "已加载 VTube Studio 模型配置: {} ({}) -> {}",
            model_name,
            model_id,
            self.model_config_manager.path,
        )
        return model_config

    async def _refresh_parameter_specs(
        self,
        model_config: VTubeStudioModelConfig,
    ) -> None:
        """用 VTube Studio 当前可注入输入参数刷新平台参数范围"""

        try:
            response = await self.client.get_input_parameters()
        except Exception as exc:
            logger.warning(
                "读取 VTube Studio 参数列表失败，沿用模型配置参数: {}",
                exc,
            )
            return

        specs_by_name: dict[str, PlatformParameterSpec] = {}
        for parameter in [
            *response.data.default_parameters,
            *response.data.custom_parameters,
        ]:
            specs_by_name[parameter.name] = PlatformParameterSpec(
                name=parameter.name,
                minimum=parameter.min,
                maximum=parameter.max,
            )
        specs = list(specs_by_name.values())
        if not specs:
            return

        model_config.parameter_specs = specs

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
            self.client.add_event_handler(event_name, handler)

        request = EventSubscriptionRequest(
            data=EventSubscriptionRequestData(
                eventName=event_name,
                subscribe=True,
                config=config or EventSubscriptionConfig(),
            ),
        )

        try:
            return await self.client.subscribe_event(request)
        except Exception:
            if handler is not None:
                self.client.remove_event_handler(event_name, handler)
            raise

    async def unsubscribe(
        self,
        event_name: EventName | str,
        handler: ListenerHandler | None = None,
    ) -> EventSubscriptionResponse | None:
        if handler is not None:
            self.client.remove_event_handler(event_name, handler)

        if handler is not None and self.client.has_event_handlers(event_name):
            return None

        try:
            return await self.client.unsubscribe_event(event_name)
        except Exception:
            if handler is not None:
                self.client.add_event_handler(event_name, handler)
            raise

    async def listen_for_api(
        self,
        timeout: float | None = None,
        max_messages: int | None = None,
    ) -> list[VTubeStudioAPIStateBroadcast]:
        async with contextlib.aclosing(
            self.discovery.listen(
                timeout=timeout,
                max_messages=max_messages,
            )
        ) as broadcasts:
            return [broadcast async for broadcast in broadcasts]

    async def send_parameter_states(
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
                parameterValues=[InjectParameterValue(id=state.name, value=state.value) for state in parameter_states],
            ),
        )
        await self.client.inject_parameter_data(request)

    async def apply_native_expressions(
        self,
        triggers: Iterable[NativeExpressionTrigger],
    ) -> None:
        """把表情解算层产出的原生触发翻译为 VTube Studio 表情激活/停用"""

        if self._expression_adapter is None:
            return
        await self._expression_adapter.apply(list(triggers), self.client)

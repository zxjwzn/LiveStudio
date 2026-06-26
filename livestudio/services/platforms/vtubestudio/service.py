"""VTube Studio 服务"""

import asyncio
import contextlib
from collections.abc import Iterable
from typing import Literal, TypeVar

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

_RequiredT = TypeVar("_RequiredT")


def _require(value: _RequiredT | None, message: str) -> _RequiredT:
    """断言依赖已就绪：为 None 时抛出统一的 RuntimeError，否则原样返回。

    收敛各属性「未初始化则抛错」的重复守卫，集中错误消息、统一风格。
    """

    if value is None:
        raise RuntimeError(message)
    return value


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
        # discovery 随服务构造而建：LAN 发现用于「连接前」找地址，不依赖连接/配置加载。
        # 传入返回最新配置的 provider，避免捕获构造期的陈旧快照（config_manager.load()
        # 会在 start 时把配置替换为新对象）。
        self._discovery = VTubeStudioDiscovery(lambda: self.config)
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

        service = _require(self._model_config_service, "当前没有已加载的模型配置")
        return _require(service.config, "当前没有已加载的模型配置")

    @property
    def model_config_manager(self) -> ConfigManager[VTubeStudioModelConfig]:
        """返回当前模型配置管理器实例"""

        service = _require(self._model_config_service, "当前没有已加载的模型配置")
        return _require(service.manager, "当前没有已加载的模型配置")

    @property
    def current_model(self) -> PlatformModelIdentity:
        """返回当前平台已加载模型身份"""

        service = _require(self._model_config_service, "当前没有已加载的模型")
        return _require(service.identity, "当前没有已加载的模型")

    @property
    def client(self) -> VTubeStudioClient:
        """返回已启动的底层客户端"""

        return _require(self._client, "VTubeStudio 尚未启动，请先调用 start()")

    @property
    def discovery(self) -> VTubeStudioDiscovery:
        """返回自动发现对象（随服务构造即可用，无需先启动）"""

        return self._discovery

    async def _do_start(self) -> None:
        """准备依赖并连接认证，连接失败时自动重连直到成功。

        资源准备（重读配置、建 client/model_config_service）与连接启动合并在这里
        完成；幂等与标志维护由 Mixin 负责。VTube Studio 的连接需在不可达时无限重试。
        """

        await self._ensure_dependencies_built()

        retry_delay = 3.0
        max_delay = 30.0
        backoff_factor = 1.5

        while True:
            try:
                await self.connect()
                await self.authenticate()
                await self.tween.start()
                logger.success("VTube Studio 已连接并完成认证")
            except VTubeStudioConnectionError as exc:
                logger.warning(f"连接 VTube Studio 失败: {exc}，{retry_delay:.1f}秒后重试...")
                # 认证阶段失败时连接可能已建立，重试前先断开，避免每轮泄漏一条 websocket
                await self._safe_disconnect()
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * backoff_factor, max_delay)
            else:
                return

    async def _ensure_dependencies_built(self) -> None:
        """重读配置并构建 client 与模型配置服务（幂等：client 已存在则跳过）。

        资源准备并入启动流程；start 时重读配置使每次启动都以最新状态部署。
        """

        if self._client is not None:
            return
        await self.config_manager.load()
        self._client = VTubeStudioClient(
            config=self.config,
            plugin_info=self.config.plugin,
        )
        self._model_config_service = PlatformModelConfigService(
            config_model=VTubeStudioModelConfig,
            model_config_dir=self.config.model_config_dir,
        )

    async def _do_stop(self) -> None:
        """停止服务并按需保存配置（唯一真正的退出：释放依赖、断开连接）"""

        await self.tween.stop()
        await self._safe_disconnect()
        await self.config_manager.save()
        if self._model_config_service is not None:
            await self._model_config_service.save()
        self._client = None
        self._model_config_service = None
        self._semantic_adapter = None
        self._expression_adapter = None

    async def _do_restart(self) -> None:
        """以新状态重新部署：断开并重连认证，保留对外契约。

        区别于 stop：不销毁 client/model_config_service，因此重启后无需重建依赖。
        重连不做无限重试——restart 是显式操作，失败时由 Mixin 的 restart() 统一
        回滚到 stop()。
        """

        await self.tween.stop()
        await self._safe_disconnect()
        await self.connect()
        await self.authenticate()
        await self.tween.start()
        logger.success("VTube Studio 已重连并完成认证")

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
        """用 VTube Studio 当前可注入输入参数补全平台参数范围。

        探测结果属于运行时瞬态，只在用户尚未配置（parameter_specs 为空）时
        填充进内存，作为开箱即用的默认；一旦用户在配置文件里配过参数范围，
        就完全尊重其取值，探测结果仅用于发现缺失项时告警，绝不覆盖。
        本方法不主动落盘——首次创建的默认已由 create_default 写入文件。
        """

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

        if model_config.parameter_specs:
            # 用户已配过参数范围：完全尊重，只对探测发现的缺失项告警，不覆盖。
            configured = {spec.name for spec in model_config.parameter_specs}
            missing = [name for name in specs_by_name if name not in configured]
            if missing:
                logger.warning(
                    "VTube Studio 可注入参数未在模型配置中声明，已忽略: {}",
                    missing,
                )
            return

        # 用户未配置：用平台探测结果填充内存运行态。
        model_config.parameter_specs = specs

    async def _safe_disconnect(self) -> None:
        """断开底层客户端连接（若已建立），吞掉断连自身异常。

        连接尚未建立或断连过程出错都不应阻断调用方的停机/重试流程，故统一在此
        收敛 ``if self._client is not None`` 判定与异常抑制。
        """

        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.disconnect()

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
        *,
        fade_time: float | None = None,
    ) -> None:
        """把表情解算层产出的原生触发翻译为 VTube Studio 表情激活/停用"""

        if self._expression_adapter is None:
            return
        await self._expression_adapter.apply(list(triggers), self.client, fade_time=fade_time)

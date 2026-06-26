"""把 VTube Studio 应用流程串起来"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from livestudio.clients.vtube_studio.models import (
    EventSubscriptionResponse,
    ExpressionActivationRequest,
    ExpressionActivationRequestData,
    ExpressionStateRequest,
    ExpressionStateRequestData,
    ExpressionStateResponse,
    ModelLoadedEvent,
    VTSEventEnvelope,
)
from livestudio.services.animations import (
    AnimationController,
    AnimationManager,
    BlinkController,
    BreathingController,
    ExpressionController,
    GazeController,
    MouthExpressionController,
    MouthSyncController,
)
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    VTubeStudioExpressionStateConfig,
    VTubeStudioModelConfig,
)
from livestudio.utils.log import logger

# 模型变更监听器：参数为 (model_id, model_name)。后端只负责广播「模型已就绪/已切换」，
# 不关心由谁消费——GUI 适配器等外部观察者据此自我刷新，从而与本应用解耦。
ModelChangedListener = Callable[[str, str], Awaitable[None] | None]


class VTubeStudioApp(AsyncServiceLifecycleMixin):
    """把 VTube Studio、音频流和动画运行流程串起来"""

    def __init__(
        self,
        *,
        animation_manager: AnimationManager,
        audio_stream: AudioStreamSource,
    ) -> None:
        self.audio_stream = audio_stream
        self.platform = VTubeStudio()
        self.animation_manager = animation_manager
        self.animation_manager.register_runtime(self.platform)
        self._model_subscription: EventSubscriptionResponse | None = None
        self._model_changed_listener: ModelChangedListener | None = None

    def set_model_changed_listener(self, listener: ModelChangedListener | None) -> None:
        """注册模型变更监听器（首次加载与运行时换模型都会触发）。

        传 None 解除监听。监听器异常被隔离，不影响模型加载主流程。
        """

        self._model_changed_listener = listener

    async def _do_start(self) -> None:
        """启动 VTube Studio 相关应用（含资源准备）。

        启动失败的回滚交由 Mixin 的 start() 统一调用 stop()（即 _do_stop）。
        """

        await self.platform.start()
        await self.load_current_model()
        await self.animation_manager.start()

    async def start_platform_for_expression_test(self) -> None:
        """启动平台并加载当前模型，但先不启动待机动画"""

        await self.platform.start()
        await self.load_current_model()

    async def connect(self) -> None:
        """连接 VTube Studio 并加载当前模型，但不启动动画控制器。

        供 GUI 把「连接」与「控制器启停」拆成两个独立动作:连接只建立平台会话与
        模型配置,动画待机由 start_controllers 单独开启。语义同
        start_platform_for_expression_test,以更贴合 GUI 的命名暴露。
        """

        await self.platform.start()
        await self.load_current_model()

    async def disconnect(self) -> None:
        """断开 VTube Studio:先停动画控制器,再停平台(镜像 _do_stop 顺序)。"""

        await self.animation_manager.stop()
        await self.platform.stop()
        self._model_subscription = None

    async def start_controllers(self) -> None:
        """启动动画控制器(待机动画)。需平台已连接。"""

        await self.animation_manager.start()

    async def stop_controllers(self) -> None:
        """停止动画控制器(幂等,未运行时为空操作)。"""

        await self.animation_manager.stop()

    async def load_current_model(self) -> None:
        """订阅模型事件并加载当前模型配置"""

        await self._subscribe_model_events()
        await self._load_active_model_config()

    async def _do_stop(self) -> None:
        """停止应用并释放资源"""

        await self.animation_manager.stop()
        await self.platform.stop()
        self._model_subscription = None

    async def _subscribe_model_events(self) -> None:
        """监听 VTube Studio 的模型加载事件"""

        if self._model_subscription is not None:
            return
        self._model_subscription = await self.platform.subscribe(
            "ModelLoadedEvent",
            self._handle_model_loaded,
        )

    async def _handle_model_loaded(self, event: VTSEventEnvelope) -> None:
        """处理模型加载事件并刷新动画控制器"""

        model_event = ModelLoadedEvent.model_validate(event.model_dump())
        if not model_event.data.model_loaded:
            return
        await self._refresh_for_model(
            model_event.data.model_id,
            model_event.data.model_name,
        )

    async def _load_active_model_config(self) -> None:
        """读取当前模型并刷新动画控制器"""

        current_model = await self.platform.client.get_current_model()
        if not current_model.data.model_loaded:
            return
        await self._refresh_for_model(
            current_model.data.model_id,
            current_model.data.model_name,
        )

    async def _refresh_for_model(self, model_id: str, model_name: str) -> None:
        """重建模型配置并同步表情与动画控制器，完成后广播模型变更"""

        model_config = await self.platform.reload_model_config(model_id, model_name)
        await self._sync_model_expressions(model_config)
        await self._apply_model_config(model_config)
        await self._notify_model_changed(model_id, model_name)

    async def _notify_model_changed(self, model_id: str, model_name: str) -> None:
        """广播模型变更：同步或异步监听器都支持，异常隔离不影响主流程。"""

        listener = self._model_changed_listener
        if listener is None:
            return
        try:
            result = listener(model_id, model_name)
            if isinstance(result, Awaitable):
                await result
        except Exception:
            logger.exception("模型变更监听器执行失败，已隔离")

    async def _fetch_expression_state(self) -> ExpressionStateResponse:
        """拉取当前模型的表情状态（含明细）"""

        return await self.platform.client.get_expression_state(
            ExpressionStateRequest(
                data=ExpressionStateRequestData(details=True),
            ),
        )

    @staticmethod
    def _snapshot_expressions(
        expressions: Sequence[Any],
    ) -> list[VTubeStudioExpressionStateConfig]:
        """把 VTube Studio 表情状态转换为可持久化的配置快照"""

        return [
            VTubeStudioExpressionStateConfig(
                name=expression.name,
                file=expression.file,
                active=expression.active,
            )
            for expression in expressions
        ]

    async def save_current_model_expressions_to_config(self) -> None:
        """将当前模型表情激活状态保存为下次模型加载时使用的配置"""

        expression_response = await self._fetch_expression_state()
        self.platform.model_config.expressions = self._snapshot_expressions(
            expression_response.data.expressions,
        )
        await self.platform.model_config_manager.save()

    async def _sync_model_expressions(self, config: VTubeStudioModelConfig) -> None:
        """按模型配置同步 VTube Studio 里的表情开关"""

        expression_response = await self._fetch_expression_state()
        if not expression_response.data.model_loaded:
            return

        expressions = expression_response.data.expressions
        if not config.expressions:
            config.expressions = self._snapshot_expressions(expressions)
            await self.platform.model_config_manager.save()
            return

        current_by_file = {expression.file: expression for expression in expressions}
        config_by_file = {expression_config.file: expression_config for expression_config in config.expressions}
        changed = False
        for expression in expressions:
            if expression.file in config_by_file:
                continue
            expression_config = VTubeStudioExpressionStateConfig(
                name=expression.name,
                file=expression.file,
                active=expression.active,
            )
            config.expressions.append(expression_config)
            config_by_file[expression.file] = expression_config
            changed = True

        for expression_config in config.expressions:
            expression_file = expression_config.file
            if expression_file not in current_by_file:
                continue
            await self.platform.client.set_expression_active(
                ExpressionActivationRequest(
                    data=ExpressionActivationRequestData(
                        expressionFile=expression_file,
                        active=expression_config.active,
                    ),
                ),
            )

        if changed:
            await self.platform.model_config_manager.save()

    async def _apply_model_config(self, config: VTubeStudioModelConfig) -> None:
        """把模型配置用到 VTube Studio 动画运行流程里"""

        runtime = self.animation_manager.get_runtime(self.platform.name)
        current_controllers = runtime.controllers
        ctrls = config.controllers

        # (key, 当前配置对象, 新建工厂)：复用判定与构造统一描述。新增控制器只加一行，
        # 复用判定（配置对象未变则沿用现有 controller）只剩一份，不会在多段分支间漂移。
        specs: list[tuple[str, Any, Callable[[], AnimationController[Any]]]] = [
            ("blink", ctrls.blink, lambda: BlinkController(runtime, "blink", ctrls.blink)),
            ("breathing", ctrls.breathing, lambda: BreathingController(runtime, "breathing", ctrls.breathing)),
            ("gaze", ctrls.gaze, lambda: GazeController(runtime, "gaze", ctrls.gaze)),
            (
                "mouth_expression",
                ctrls.mouth_expression,
                lambda: MouthExpressionController(runtime, "mouth_expression", ctrls.mouth_expression),
            ),
            (
                "mouth_sync",
                ctrls.mouth_sync,
                lambda: MouthSyncController(runtime, "mouth_sync", ctrls.mouth_sync, self.audio_stream),
            ),
        ]

        controllers: list[AnimationController[Any]] = []
        for key, cfg, factory in specs:
            existing = current_controllers.get(key)
            controllers.append(existing if existing is not None and existing.config is cfg else factory())

        # 表情解算控制器（一次性，额外依赖 expression_profile，单列于表外）
        controllers.append(ExpressionController(runtime, "expression", ctrls.expression, config.expression_profile))

        await runtime.reload_controllers(controllers)

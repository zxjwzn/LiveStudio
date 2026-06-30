"""把 VTube Studio 应用流程串起来"""

from livestudio.app.base import BasePlatformApp
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
    AnimationManager,
    BlinkController,
    BreathingController,
    ExpressionController,
    GazeController,
    MouthExpressionController,
    MouthSyncController,
)
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.expression.models import NativeExpressionTrigger
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    VTubeStudioExpressionStateConfig,
    VTubeStudioModelConfig,
)

# MCP/手动来源切换原生表情独占的作用域,与情绪解算(emotion)互不干扰(见 VTSExpressionAdapter)。
_NATIVE_SCOPE = "manual"


class VTubeStudioApp(BasePlatformApp[VTubeStudio, VTubeStudioModelConfig]):
    """把 VTube Studio、音频流和动画运行流程串起来"""

    def __init__(
        self,
        *,
        animation_manager: AnimationManager,
        audio_stream: AudioStreamSource,
    ) -> None:
        super().__init__(
            platform=VTubeStudio(),
            animation_manager=animation_manager,
            audio_stream=audio_stream,
        )
        self._model_subscription: EventSubscriptionResponse | None = None
        # 当前由手动/MCP 来源激活的原生表情名镜像(adapter 为集合替换式,toggle 时把整集下发)。
        self._active_native: set[str] = set()

    def _on_disconnected(self) -> None:
        """断开后清空模型事件订阅句柄与原生表情镜像,使下次连接重新订阅/对齐"""

        self._model_subscription = None
        self._active_native = set()

    # --- 原生表情(exp3,可激活/取消的 toggle;VTS 特有,供上层消费者直接调用) ---

    def native_expressions(self) -> list[str]:
        """当前模型可 toggle 的 exp3 表情名列表;未加载模型时为空。"""

        try:
            model_config = self.platform.model_config
        except RuntimeError:
            return []
        return [expression.name for expression in model_config.expressions]

    def active_native_expressions(self) -> set[str]:
        """当前由手动/MCP 来源激活的 exp3 表情名集合快照。"""

        return set(self._active_native)

    async def set_native_expression(self, name: str, active: bool) -> bool:
        """激活/取消单个 exp3 表情,返回操作后该表情是否处于激活态。

        把更新后的整集下发给平台 adapter(集合替换式,由 adapter diff 增删)。需已连接。
        name 不在当前模型表情清单中时 adapter 会告警跳过,返回值仍按本地镜像反映意图。
        """

        target = set(self._active_native)
        if active:
            target.add(name)
        else:
            target.discard(name)
        await self._apply_native(target)
        return name in self._active_native

    async def clear_native_expressions(self) -> None:
        """取消所有已激活的 exp3 表情。需已连接。"""

        await self._apply_native(set())

    async def _apply_native(self, target: set[str]) -> None:
        """把目标激活集合下发给平台 adapter(diff 增删),成功后更新本地镜像。"""

        triggers = [NativeExpressionTrigger(platform=self.platform.name, native_ref=name) for name in target]
        await self.platform.apply_native_expressions(triggers, scope=_NATIVE_SCOPE)
        self._active_native = target

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

    async def _reload_model_config(self, model_id: str, model_name: str) -> VTubeStudioModelConfig:
        """按当前 VTube Studio 模型重建并加载模型级配置"""

        return await self.platform.reload_model_config(model_id, model_name)

    async def _fetch_expression_state(self) -> ExpressionStateResponse:
        """拉取当前模型的表情状态（含明细）"""

        return await self.platform.client.get_expression_state(
            ExpressionStateRequest(
                data=ExpressionStateRequestData(details=True),
            ),
        )

    async def _sync_native_state(self, config: VTubeStudioModelConfig) -> None:
        """按模型配置同步 VTube Studio 里的表情开关"""

        expression_response = await self._fetch_expression_state()
        if not expression_response.data.model_loaded:
            return

        expressions = expression_response.data.expressions
        if not config.expressions:
            config.expressions = [
                VTubeStudioExpressionStateConfig(name=expr.name, file=expr.file, active=expr.active)
                for expr in expressions
            ]
            await self.platform.model_config_manager.save()
            self.platform.refresh_expression_adapter(config)
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
        self.platform.refresh_expression_adapter(config)

    async def _apply_model_config(self, config: VTubeStudioModelConfig) -> None:
        """把模型配置用到 VTube Studio 动画运行流程里"""

        runtime = self.animation_manager.get_runtime(self.platform.name)
        ctrls = config.controllers
        await runtime.reload_controllers(
            [
                BlinkController(runtime, "blink", ctrls.blink),
                BreathingController(runtime, "breathing", ctrls.breathing),
                GazeController(runtime, "gaze", ctrls.gaze),
                MouthExpressionController(runtime, "mouth_expression", ctrls.mouth_expression),
                MouthSyncController(runtime, "mouth_sync", ctrls.mouth_sync, self.audio_stream),
                ExpressionController(runtime, "expression", ctrls.expression, config.expression_profile),
            ]
        )

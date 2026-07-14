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
    TTSpeakController,
)
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    VTubeStudioExpressionStateConfig,
    VTubeStudioModelConfig,
)


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

    def _on_disconnected(self) -> None:
        """断开后清空模型事件订阅句柄，使下次连接重新订阅。"""

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
                VTubeStudioExpressionStateConfig(name=expr.name, file=expr.file, active=expr.active) for expr in expressions
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
                TTSpeakController(runtime, "tts_speak", ctrls.tts_speak, self.audio_stream),
            ]
        )

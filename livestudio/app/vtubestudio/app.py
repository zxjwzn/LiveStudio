"""把 VTube Studio 应用流程串起来"""

from collections.abc import Sequence
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
    BodySwingController,
    BreathingController,
    ExpressionController,
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

    async def initialize(self) -> None:
        """初始化应用依赖"""

        if self._initialized:
            return
        await self.platform.initialize()
        await self.animation_manager.initialize()
        self._mark_initialized()

    async def start(self) -> None:
        """启动 VTube Studio 相关应用"""

        if self._started:
            return
        if not self._initialized:
            await self.initialize()
        try:
            await self.platform.start()
            await self.load_current_model()
            await self.animation_manager.start()
        except Exception:
            await self.stop()
            raise
        self._mark_started()

    async def start_platform_for_expression_test(self) -> None:
        """启动平台并加载当前模型，但先不启动待机动画"""

        await self.platform.start()
        await self.load_current_model()

    async def load_current_model(self) -> None:
        """订阅模型事件并加载当前模型配置"""

        await self._subscribe_model_events()
        await self._load_active_model_config()

    async def stop(self) -> None:
        """停止应用并释放资源"""

        if not self._initialized:
            return
        await self.animation_manager.stop()
        await self.platform.stop()
        self._model_subscription = None
        self._mark_stopped(reset_initialized=True)

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
        """重建模型配置并同步表情与动画控制器"""

        model_config = await self.platform.reload_model_config(model_id, model_name)
        await self._sync_model_expressions(model_config)
        await self._apply_model_config(model_config)

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
        config_by_file = {
            expression_config.file: expression_config
            for expression_config in config.expressions
        }
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
        controllers: list[AnimationController[Any]] = []

        # 眨眼控制器
        if (current := current_controllers.get("blink")) is not None and current.config is config.controllers.blink:
            controllers.append(current)
        else:
            controllers.append(BlinkController(runtime, "blink", config.controllers.blink))

        # 呼吸控制器
        if (current := current_controllers.get("breathing")) is not None and current.config is config.controllers.breathing:
            controllers.append(current)
        else:
            controllers.append(BreathingController(runtime, "breathing", config.controllers.breathing))

        # 身体摇摆控制器
        if (current := current_controllers.get("body_swing")) is not None and current.config is config.controllers.body_swing:
            controllers.append(current)
        else:
            controllers.append(BodySwingController(runtime, "body_swing", config.controllers.body_swing))

        # 嘴部表情控制器
        if (current := current_controllers.get("mouth_expression")) is not None and current.config is config.controllers.mouth_expression:
            controllers.append(current)
        else:
            controllers.append(MouthExpressionController(runtime, "mouth_expression", config.controllers.mouth_expression))

        # 嘴部同步控制器（需要额外的 audio_stream）
        if (current := current_controllers.get("mouth_sync")) is not None and current.config is config.controllers.mouth_sync:
            controllers.append(current)
        else:
            controllers.append(
                MouthSyncController(
                    runtime,
                    "mouth_sync",
                    config.controllers.mouth_sync,
                    self.audio_stream,
                )
            )

        # 表情解算控制器（一次性，需要额外的 expression_profile）
        controllers.append(
            ExpressionController(
                runtime,
                "expression",
                config.controllers.expression,
                config.expression_profile,
            )
        )

        await runtime.reload_controllers(controllers)

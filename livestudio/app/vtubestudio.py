"""VTube Studio 应用编排。"""

from __future__ import annotations

from livestudio.clients.vtube_studio.models import (
    EventSubscriptionResponse,
    ModelLoadedEvent,
    VTSEventEnvelope,
)
from livestudio.services.animations import (
    AnimationController,
    AnimationManager,
    BlinkController,
    BodySwingController,
    BreathingController,
    ControllerSettings,
    MouthExpressionController,
)
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    VTubeStudioModelConfig,
)


class VTubeStudioApp:
    """编排 VTube Studio 平台、音频流与动画运行时。"""

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
        """初始化应用依赖。"""

        await self.platform.initialize()
        await self.animation_manager.initialize()

    async def start(self) -> None:
        """启动 VTube Studio 应用。"""

        await self.platform.start()
        await self._subscribe_model_events()
        await self._load_active_model_config()
        await self.animation_manager.start()

    async def stop(self) -> None:
        """停止应用并释放资源。"""

        await self.animation_manager.stop()
        await self.platform.stop()
        self._model_subscription = None

    async def _subscribe_model_events(self) -> None:
        """订阅 VTube Studio 模型加载事件。"""

        if self._model_subscription is not None:
            return
        self._model_subscription = await self.platform.subscribe(
            "ModelLoadedEvent",
            self._handle_model_loaded,
        )

    async def _handle_model_loaded(self, event: VTSEventEnvelope) -> None:
        """处理模型加载事件并刷新动画控制器。"""

        model_event = ModelLoadedEvent.model_validate(event.model_dump())
        if not model_event.data.model_loaded:
            return
        model_config = await self.platform.reload_model_config(
            model_event.data.model_id,
            model_event.data.model_name,
        )
        await self._apply_model_config(model_config)

    async def _load_active_model_config(self) -> None:
        """读取当前模型并刷新动画控制器。"""

        current_model = await self.platform.client.get_current_model()
        if not current_model.data.model_loaded:
            return
        model_config = await self.platform.reload_model_config(
            current_model.data.model_id,
            current_model.data.model_name,
        )
        await self._apply_model_config(model_config)

    async def _apply_model_config(self, config: VTubeStudioModelConfig) -> None:
        """应用模型配置到 VTube Studio 动画运行时。"""

        runtime = self.animation_manager.get_runtime(self.platform.name)
        controllers: list[AnimationController[ControllerSettings]] = [
            BlinkController(runtime, "blink", config.controllers.blink),
            BreathingController(runtime, "breathing", config.controllers.breathing),
            BodySwingController(runtime, "body_swing", config.controllers.body_swing),
            MouthExpressionController(
                runtime,
                "mouth_expression",
                config.controllers.mouth_expression,
            ),
        ]
        await runtime.reload_controllers(controllers)

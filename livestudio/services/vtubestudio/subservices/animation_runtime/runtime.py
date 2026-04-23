"""动画运行时子服务。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from livestudio.log import logger
from livestudio.services.audio_input import AudioInputService
from livestudio.tween import TweenMode

from ..base import VTubeStudioSubservice
from .controllers import BlinkController, BreathingController, MouthSyncController
from .controllers.base import AnimationController
from .models import (
    AnimationRuntimeConfigFile,
    AnimationType,
    ResolvedTemplateAction,
    TemplateScalar,
)
from .template_repository import AnimationTemplateRepository


class AnimationRuntimeService(VTubeStudioSubservice[AnimationRuntimeConfigFile]):
    """统一管理循环动画、一次性动画与模板动画。"""

    def __init__(self, *, config_path: str | Path | None = None) -> None:
        super().__init__("animation_runtime", AnimationRuntimeConfigFile, config_path=config_path)
        self._controllers: dict[str, AnimationController[Any]] = {}
        self._template_repository: AnimationTemplateRepository | None = None
        self._audio_input_service: AudioInputService | None = None

    @property
    def controllers(self) -> dict[str, AnimationController[Any]]:
        return dict(self._controllers)

    @property
    def template_repository(self) -> AnimationTemplateRepository:
        repository = self._template_repository
        if repository is None:
            raise RuntimeError("动画模板仓库尚未初始化")
        return repository

    @property
    def audio_input_service(self) -> AudioInputService | None:
        return self._audio_input_service

    def bind_audio_input_service(self, audio_input_service: AudioInputService) -> None:
        self._audio_input_service = audio_input_service

    async def initialize(self) -> None:
        config = self.config.config
        repository = AnimationTemplateRepository(config.resolve_template_dir())
        await repository.load()
        self._template_repository = repository
        self._controllers = self._build_controllers()
        logger.info("动画运行时已初始化，控制器数量: {}", len(self._controllers))

    async def start(self) -> None:
        if not self.config.config.enabled:
            logger.info("动画运行时逻辑已禁用，跳过控制器启动")
            return
        if self.config.config.auto_start_idle:
            await self.start_idle_controllers()

    async def stop(self) -> None:
        await self.stop_all_controllers()

    async def close(self) -> None:
        await self.stop()

    async def save_config(self) -> None:
        await self.config_manager.save()

    async def start_idle_controllers(self) -> None:
        for controller in self._controllers.values():
            if controller.animation_type is AnimationType.IDLE:
                await controller.start()

    async def stop_idle_controllers(self) -> None:
        for controller in self._controllers.values():
            if controller.animation_type is AnimationType.IDLE:
                await controller.stop_without_wait()

    async def stop_all_controllers(self) -> None:
        for controller in self._controllers.values():
            await controller.stop_without_wait()

    async def execute_oneshot(self, controller_name: str, *, parameters: Mapping[str, TemplateScalar] | None = None) -> None:
        controller = self._require_controller(controller_name)
        if controller.animation_type is not AnimationType.ONESHOT:
            raise ValueError(f"控制器 {controller_name} 不是一次性控制器")
        await controller.start(parameters=parameters or {})
        await controller.stop()

    async def play_template(
        self,
        template_name: str,
        *,
        parameters: Mapping[str, TemplateScalar] | None = None,
    ) -> None:
        playback = self.template_repository.render(
            template_name,
            parameters=parameters,
        )
        tasks = []
        for action in playback.actions:
            tasks.append(asyncio.create_task(self._run_template_action(action)))
        if tasks:
            await asyncio.gather(*tasks)

    async def _run_template_action(self, action: object) -> None:
        resolved_action = action if isinstance(action, ResolvedTemplateAction) else ResolvedTemplateAction.model_validate(action)
        if resolved_action.delay > 0:
            await asyncio.sleep(resolved_action.delay)
        await self.vtubestudio.tween.tween(
            parameter_name=resolved_action.parameter,
            end_value=resolved_action.to,
            duration=resolved_action.duration,
            easing=resolved_action.easing,
            start_value=resolved_action.from_value,
            mode=resolved_action.mode,
            priority=resolved_action.priority,
            keep_alive=resolved_action.keep_alive,
        )

    def _build_controllers(self) -> dict[str, AnimationController[Any]]:
        config = self.config.config
        return {
            "blink": BlinkController(self, "blink", config.blink),
            "breathing": BreathingController(self, "breathing", config.breathing),
            "mouth_sync": MouthSyncController(self, "mouth_sync", config.mouth_sync),
        }

    def _require_controller(self, name: str) -> AnimationController[Any]:
        controller = self._controllers.get(name)
        if controller is None:
            raise KeyError(f"未知动画控制器: {name}")
        return controller

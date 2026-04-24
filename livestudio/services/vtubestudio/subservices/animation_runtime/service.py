"""动画运行时子服务。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from livestudio.log import logger
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.tween import TweenMode

from .....clients.vtube_studio.models import ModelLoadedEvent
from ...model_config import VTubeStudioModelConfigRepository
from ..base import VTubeStudioSubservice
from .controllers import BlinkController, BreathingController, MouthSyncController
from .controllers.base import AnimationController
from .models import (
    AnimationRuntimeConfigFile,
    AnimationType,
    ModelAnimationConfig,
    ResolvedTemplateAction,
    TemplateScalar,
)
from .template_repository import AnimationTemplateRepository


class AnimationRuntimeService(VTubeStudioSubservice[AnimationRuntimeConfigFile]):
    """统一管理循环动画、一次性动画与模板动画。"""

    def __init__(self) -> None:
        super().__init__(
            "animation_runtime",
            AnimationRuntimeConfigFile,
            Path("config") / "vtubestudio_services" / "animation_runtime.yaml",
        )
        self._controllers: dict[str, AnimationController[Any]] = {}
        self._template_repository: AnimationTemplateRepository | None = None
        self._audio_stream: AudioStreamSource | None = None
        self._model_config_repository = VTubeStudioModelConfigRepository()
        self._reload_lock = asyncio.Lock()
        self._reload_task: asyncio.Task[None] | None = None

    @property
    def controllers(self) -> dict[str, AnimationController[Any]]:
        return self._controllers

    @property
    def template_repository(self) -> AnimationTemplateRepository:
        if self._template_repository is None:
            raise RuntimeError("动画模板仓库尚未初始化")
        return self._template_repository

    async def initialize(self) -> None:
        config = self.config.config
        repository = AnimationTemplateRepository(Path(config.template_dir))
        await repository.load()
        self._template_repository = repository
        logger.info("动画运行时已初始化，等待当前模型动画配置")

    async def start(self) -> None:
        if not self.config.config.enabled:
            logger.info("动画运行时逻辑已禁用，跳过控制器启动")
            return
        await self.vtubestudio.subscribe(
            "ModelLoadedEvent",
            self._handle_model_loaded_event,
        )
        await self.reload_current_model_animation_config(
            start_idle=self.config.config.auto_start_idle,
        )

    async def stop(self) -> None:
        await self.vtubestudio.unsubscribe(
            "ModelLoadedEvent",
            self._handle_model_loaded_event,
        )
        if self._reload_task is not None:
            self._reload_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reload_task
        self._reload_task = None
        await self.stop_all_controllers()

    async def close(self) -> None:
        await self.stop()

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

    async def reload_current_model_animation_config(
        self,
        *,
        start_idle: bool,
    ) -> None:
        """按当前 VTS 模型重新加载动画控制器配置。"""

        async with self._reload_lock:
            await self.stop_all_controllers()
            self._controllers = {}

            current_model_response = await self.vtubestudio.client.get_current_model()
            current_model = current_model_response.data
            model_config_manager = (
                await self._model_config_repository.load_current_model_config(
                    current_model,
                )
            )
            if model_config_manager is None:
                logger.info("当前未加载模型，动画控制器保持停止")
                return

            self._rebuild_controllers(model_config_manager.config.animation)
            logger.info(
                "已加载模型动画配置: {} ({})，控制器数量: {}",
                current_model.model_name,
                current_model.model_id,
                len(self._controllers),
            )
            if start_idle:
                await self.start_idle_controllers()

    async def execute_oneshot(
        self,
        controller_name: str,
        *,
        parameters: Mapping[str, TemplateScalar] | None = None,
    ) -> None:
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
        resolved_action = (
            action
            if isinstance(action, ResolvedTemplateAction)
            else ResolvedTemplateAction.model_validate(action)
        )
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

    async def _handle_model_loaded_event(self, event: object) -> None:
        payload = (
            event.model_dump(by_alias=True) if isinstance(event, BaseModel) else event
        )
        model_loaded_event = ModelLoadedEvent.model_validate(payload)
        if not model_loaded_event.data.model_loaded:
            logger.info("收到模型卸载事件，停止动画控制器")
            await self.stop_all_controllers()
            self._controllers = {}
            return

        logger.info(
            "收到模型加载事件，准备加载动画配置: {} ({})",
            model_loaded_event.data.model_name,
            model_loaded_event.data.model_id,
        )
        existing_task = self._reload_task
        if existing_task is not None and not existing_task.done():
            existing_task.cancel()

        self._reload_task = asyncio.create_task(
            self._reload_current_model_animation_config_after_event(),
        )

    async def _reload_current_model_animation_config_after_event(self) -> None:
        try:
            await self.reload_current_model_animation_config(
                start_idle=self.config.config.auto_start_idle,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("模型加载后刷新动画配置失败")

    def _rebuild_controllers(self, config: ModelAnimationConfig) -> None:
        self._controllers = {
            "blink": BlinkController(self, "blink", config.blink),
            "breathing": BreathingController(self, "breathing", config.breathing),
            "mouth_sync": MouthSyncController(self, "mouth_sync", config.mouth_sync),
        }

    def _require_controller(self, name: str) -> AnimationController[Any]:
        controller = self._controllers.get(name)
        if controller is None:
            raise KeyError(f"未知动画控制器: {name}")
        return controller

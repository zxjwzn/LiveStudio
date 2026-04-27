"""单平台动画运行时。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from livestudio.log import logger
from livestudio.services.platforms import PlatformService

from .controllers import AnimationController, AnimationType, ControllerSettings
from .templates import AnimationTemplatePlayer, LoadedTemplateInfo


class PlatformAnimationRuntime:
    """管理单个平台的动画模板与控制器生命周期。"""

    def __init__(
        self,
        platform: PlatformService,
        template_player: AnimationTemplatePlayer,
        controllers: Iterable[AnimationController[ControllerSettings]] | None = None,
    ) -> None:
        self._platform = platform
        self._template_player = template_player
        self._controllers: dict[str, AnimationController[ControllerSettings]] = {}
        self._initialized = False
        self._started = False

        for controller in controllers or ():
            self.register_controller(controller)

    @property
    def platform(self) -> PlatformService:
        """返回当前运行时绑定的平台服务。"""

        return self._platform

    @property
    def platform_name(self) -> str:
        """返回当前运行时的平台名称。"""

        return self._platform.name

    @property
    def template_player(self) -> AnimationTemplatePlayer:
        """返回当前平台模板播放器。"""

        return self._template_player

    @property
    def controllers(self) -> dict[str, AnimationController[ControllerSettings]]:
        """返回控制器快照。"""

        return dict(self._controllers)

    @property
    def is_initialized(self) -> bool:
        """运行时是否已初始化。"""

        return self._initialized

    @property
    def is_started(self) -> bool:
        """运行时是否已启动。"""

        return self._started

    async def initialize(self) -> None:
        """加载当前平台的动画模板。"""

        await self._template_player.load()
        self._initialized = True
        logger.info("平台动画运行时已初始化: {}", self.platform_name)

    async def restart(self) -> None:
        """重启当前平台动画运行时。"""

        await self.stop()
        await self.initialize()
        await self.start()

    async def start(self) -> None:
        """启动当前平台所有启用的 idle 控制器。"""

        if self._started:
            return
        if not self._initialized:
            await self.initialize()

        idle_controllers = [
            controller
            for controller in self._controllers.values()
            if controller.animation_type is AnimationType.IDLE
        ]
        results = await asyncio.gather(
            *(controller.start() for controller in idle_controllers),
        )
        self._started = True
        logger.info(
            "平台动画运行时已启动: {}，启动 idle 控制器 {} 个",
            self.platform_name,
            sum(1 for result in results if result),
        )

    async def stop(self) -> None:
        """停止当前平台全部控制器。"""

        controllers = tuple(self._controllers.values())
        await asyncio.gather(
            *(controller.stop_without_wait() for controller in controllers),
        )
        self._started = False
        logger.info("平台动画运行时已停止: {}", self.platform_name)

    async def reload_templates(self) -> None:
        """重新加载当前平台动画模板。"""

        await self._template_player.reload()

    async def reload_controllers(
        self,
        controllers: Iterable[AnimationController[ControllerSettings]],
    ) -> None:
        """重新加载当前平台控制器。"""

        was_started = self._started
        await self.stop()
        self._controllers = {}
        for controller in controllers:
            self.register_controller(controller)
        if was_started:
            await self.start()

    def list_templates(self) -> list[LoadedTemplateInfo]:
        """返回当前平台已加载模板摘要。"""

        return self._template_player.list_loaded_templates()

    def register_controller(
        self,
        controller: AnimationController[ControllerSettings],
    ) -> None:
        """注册当前平台的控制器实例。"""

        if controller.name in self._controllers:
            raise ValueError(
                f"平台 {self.platform_name} 已存在动画控制器: {controller.name}",
            )
        self._controllers[controller.name] = controller

    async def unregister_controller(self, name: str) -> None:
        """停止并移除当前平台的控制器。"""

        controller = self._controllers.pop(name, None)
        if controller is not None:
            await controller.stop_without_wait()

    def get_controller(self, name: str) -> AnimationController[ControllerSettings]:
        """获取当前平台的控制器。"""

        controller = self._controllers.get(name)
        if controller is None:
            raise KeyError(f"平台 {self.platform_name} 未注册动画控制器: {name}")
        return controller

    async def start_controller(self, name: str, **kwargs: object) -> bool:
        """启动指定控制器。"""

        return await self.get_controller(name).start(**kwargs)

    async def stop_controller(self, name: str) -> None:
        """停止指定控制器。"""

        await self.get_controller(name).stop()

    async def execute_controller(self, name: str, **kwargs: object) -> bool:
        """执行指定一次性控制器。"""

        controller = self.get_controller(name)
        if controller.animation_type is not AnimationType.ONESHOT:
            raise ValueError(
                f"控制器不是一次性动画，不能通过 execute_controller 执行: {name}",
            )
        return await controller.start(**kwargs)

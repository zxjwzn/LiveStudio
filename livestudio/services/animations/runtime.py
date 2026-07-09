"""单平台动画运行时"""

import asyncio
from collections.abc import Iterable
from typing import Any

from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.services.platforms import PlatformService
from livestudio.utils.log import logger

from .controllers import AnimationController, AnimationType
from .templates import AnimationTemplatePlayer, LoadedTemplateInfo


class PlatformAnimationRuntime(AsyncServiceLifecycleMixin):
    """管理单个平台的动画模板与控制器生命周期"""

    def __init__(
        self,
        platform: PlatformService,
        template_player: AnimationTemplatePlayer,
        controllers: Iterable[AnimationController[Any]] | None = None,
    ) -> None:
        self._platform = platform
        self._template_player = template_player
        self._controllers: dict[str, AnimationController[Any]] = {}

        if template_player.platform is not platform:
            raise ValueError(
                f"动画模板播放器绑定的平台与运行时平台不一致: {template_player.platform.name} != {platform.name}",
            )

        for controller in controllers or ():
            self.register_controller(controller)

    @property
    def platform(self) -> PlatformService:
        """返回当前运行时绑定的平台服务"""

        return self._platform

    @property
    def platform_name(self) -> str:
        """返回当前运行时的平台名称"""

        return self._platform.name

    @property
    def template_player(self) -> AnimationTemplatePlayer:
        """返回当前平台模板播放器"""

        return self._template_player

    @property
    def controllers(self) -> dict[str, AnimationController[Any]]:
        """返回控制器快照"""

        return dict(self._controllers)

    async def get_semantic_value(self, action: str) -> float | None:
        """查询语义动作瞬时值"""

        return await self._platform.get_semantic_value(action)

    async def _do_start(self) -> None:
        """加载动画模板并启动当前平台所有已开启的待机控制器。

        启动失败时不在此自行回滚——交由 Mixin 的 start() 统一调用 _do_stop
        （取消全部控制器）回滚，避免重复取消。
        """

        await self._template_player.load()
        idle_controllers = [
            controller for controller in self._controllers.values() if controller.animation_type is AnimationType.IDLE
        ]
        results = await asyncio.gather(
            *(controller.start() for controller in idle_controllers),
        )
        logger.info(
            "平台动画运行时已启动: {}，启动 idle 控制器 {} 个",
            self.platform_name,
            sum(1 for result in results if result),
        )

    async def _do_stop(self) -> None:
        """停止当前平台全部控制器"""

        controllers = tuple(self._controllers.values())
        await asyncio.gather(
            *(controller.cancel() for controller in controllers),
        )
        logger.info("平台动画运行时已停止: {}", self.platform_name)

    async def reload_templates(self) -> None:
        """重新加载当前平台动画模板"""

        await self._template_player.reload()

    async def reload_controllers(
        self,
        controllers: Iterable[AnimationController[Any]],
    ) -> None:
        """热替换控制器,保留各控制器的运行态(按名匹配)。

        换模型时:取消旧控制器、注册新控制器,仅重启替换前在跑的那些(按名匹配)--用户
        单独关掉的控制器不会被重新启动。新模型配置中禁用的由 start() 守卫跳过,不会强制启动。

        活跃态以「runtime 已 start 或有控制器实际在跑」判定,而非仅 ``_started``:仪表盘用
        ``start_controller`` 单独起控制器时会绕过 ``runtime.start()``,``_started`` 仍为 False,
        若据此跳过停启会留下孤儿任务(持续注入参数、断开后向失效适配器报 NotImplementedError)。
        首次加载(注册表空、无在跑)不启动任何控制器,首次全量启动由后续 start() 负责。
        """

        next_controllers = tuple(controllers)
        if not next_controllers:
            raise ValueError("重新加载控制器时至少需要提供一个控制器")

        # 记下替换前各控制器的运行态(按名),用于换模型后按原状态重启新控制器。
        was_started = self._started
        running_names = {
            name
            for name, controller in self._controllers.items()
            if controller.is_running
        }
        active = was_started or bool(running_names)

        # 不走 stop()/start() 以免触发幂等守卫;_started 仅在原已 start 时同步翻转,
        # 单独起控制器场景保持 False(runtime 服务本身未 start)。
        if active:
            await self._do_stop()
            if was_started:
                self._mark_stopped()
        self._controllers = {}
        for controller in next_controllers:
            self.register_controller(controller)
        if active:
            # 仅重启替换前在跑的控制器(按名匹配),保留用户单独关闭的意图。不走 _do_start--
            # 它会启动全部 idle,会把用户关掉的也重新打开。模板不在此重载(平台级、不随模型变)。
            to_start = [
                controller
                for name, controller in self._controllers.items()
                if name in running_names
                and controller.animation_type is AnimationType.IDLE
            ]
            if to_start:
                await asyncio.gather(
                    *(controller.start() for controller in to_start)
                )
            if was_started:
                self._mark_started()

    def list_templates(self) -> list[LoadedTemplateInfo]:
        """返回当前平台已加载模板摘要"""

        return self._template_player.list_loaded_templates()

    def register_controller(
        self,
        controller: AnimationController[Any],
    ) -> None:
        """注册当前平台的控制器实例"""

        if controller.runtime is not self:
            raise ValueError(
                f"动画控制器绑定的运行时与目标运行时不一致: {controller.name}",
            )
        if controller.name in self._controllers:
            raise ValueError(
                f"平台 {self.platform_name} 已存在动画控制器: {controller.name}",
            )
        self._controllers[controller.name] = controller

    async def unregister_controller(self, name: str) -> None:
        """停止并移除当前平台的控制器"""

        controller = self._controllers.pop(name, None)
        if controller is not None:
            await controller.cancel()

    def get_controller(self, name: str) -> AnimationController[Any]:
        """获取当前平台的控制器"""

        controller = self._controllers.get(name)
        if controller is None:
            raise KeyError(f"平台 {self.platform_name} 未注册动画控制器: {name}")
        return controller

    async def start_controller(self, name: str, **kwargs: object) -> bool:
        """启动指定控制器"""

        return await self.get_controller(name).start(**kwargs)

    async def stop_controller(self, name: str) -> None:
        """停止指定控制器"""

        await self.get_controller(name).stop()

    async def execute_controller(self, name: str, **kwargs: object) -> bool:
        """执行指定一次性控制器"""

        controller = self.get_controller(name)
        if controller.animation_type is not AnimationType.ONESHOT:
            raise ValueError(
                f"控制器不是一次性动画，不能通过 execute_controller 执行: {name}",
            )
        return await controller.start(**kwargs)

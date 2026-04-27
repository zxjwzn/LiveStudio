"""动画运行时管理器。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from livestudio.log import logger
from livestudio.services.platforms import PlatformService

from .controllers import AnimationController, ControllerSettings
from .runtime import PlatformAnimationRuntime
from .templates import AnimationTemplatePlayer


class AnimationManager:
    """管理全部平台动画运行时。"""

    def __init__(
        self,
        *,
        template_root: Path = Path("resources") / "animations",
    ) -> None:
        self.template_root = template_root
        self._runtimes: dict[str, PlatformAnimationRuntime] = {}
        self._initialized = False
        self._started = False

    @property
    def runtimes(self) -> dict[str, PlatformAnimationRuntime]:
        """返回平台动画运行时快照。"""

        return dict(self._runtimes)

    @property
    def is_initialized(self) -> bool:
        """动画管理器是否已初始化。"""

        return self._initialized

    @property
    def is_started(self) -> bool:
        """动画管理器是否已启动。"""

        return self._started

    def register_runtime(
        self,
        platform: PlatformService,
    ) -> None:
        """为平台创建并注册动画运行时。"""

        if platform.name in self._runtimes:
            raise ValueError(f"平台动画运行时已存在: {platform.name}")

        template_player = AnimationTemplatePlayer(
            tween=platform.tween,
            template_dir=self.template_root / platform.name,
        )
        runtime = PlatformAnimationRuntime(
            platform=platform,
            template_player=template_player,
        )
        self._runtimes[platform.name] = runtime

    async def unregister_runtime(self, platform_name: str) -> None:
        """停止并移除平台动画运行时。"""

        runtime = self._runtimes.pop(platform_name, None)
        if runtime is not None:
            await runtime.stop()

    def get_runtime(self, platform_name: str) -> PlatformAnimationRuntime:
        """获取指定平台动画运行时。"""

        runtime = self._runtimes.get(platform_name)
        if runtime is None:
            raise KeyError(f"未知平台动画运行时: {platform_name}")
        return runtime

    def register_controller(
        self,
        platform_name: str,
        controller: AnimationController[ControllerSettings],
    ) -> None:
        """向指定平台运行时注册控制器实例。"""

        self.get_runtime(platform_name).register_controller(
            controller,
        )

    async def initialize(self) -> None:
        """初始化全部平台动画运行时。"""

        await asyncio.gather(
            *(runtime.initialize() for runtime in self._runtimes.values()),
        )
        self._initialized = True
        logger.info("动画管理器已初始化，平台运行时 {} 个", len(self._runtimes))

    async def start(self) -> None:
        """启动全部平台动画运行时。"""

        if self._started:
            return
        if not self._initialized:
            await self.initialize()
        await asyncio.gather(*(runtime.start() for runtime in self._runtimes.values()))
        self._started = True
        logger.info("动画管理器已启动")

    async def stop(self) -> None:
        """停止全部平台动画运行时。"""

        await asyncio.gather(*(runtime.stop() for runtime in self._runtimes.values()))
        self._started = False
        logger.info("动画管理器已停止")

    async def restart(self) -> None:
        """重启动画管理器。"""

        await self.stop()
        await self.initialize()
        await self.start()

    async def reload_templates(self, platform_name: str | None = None) -> None:
        """重载指定平台或全部平台的动画模板。"""

        if platform_name is not None:
            await self.get_runtime(platform_name).reload_templates()
            return
        await asyncio.gather(
            *(runtime.reload_templates() for runtime in self._runtimes.values()),
        )

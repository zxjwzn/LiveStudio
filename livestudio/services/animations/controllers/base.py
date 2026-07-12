"""动画控制器抽象"""

import asyncio
import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

from livestudio.utils.log import logger

from .config import ControllerSettings
from .models import AnimationType

if TYPE_CHECKING:
    from livestudio.services.animations.runtime import PlatformAnimationRuntime

ConfigT = TypeVar("ConfigT", bound=ControllerSettings)


class AnimationController(ABC, Generic[ConfigT]):
    """动画控制器统一抽象"""

    def __init__(
        self,
        runtime: "PlatformAnimationRuntime",
        name: str,
        config: ConfigT,
    ) -> None:
        self._runtime = runtime
        self._name = name
        self._config = config
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()

    @property
    def runtime(self) -> "PlatformAnimationRuntime":
        return self._runtime

    @property
    def name(self) -> str:
        return self._name

    @property
    def config(self) -> ConfigT:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    @abstractmethod
    def animation_type(self) -> AnimationType:
        """控制器类型"""

    async def start(self, **kwargs: object) -> bool:
        async with self._lifecycle_lock:
            if self.is_running:
                logger.debug("动画控制器 {} 已在运行", self.name)
                return False
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(**kwargs))
            return True

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            task = self._task
            self._stop_event.set()
            self._task = None
        if task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def cancel(self) -> None:
        """取消控制器任务，不等待控制器自行结束。"""

        async with self._lifecycle_lock:
            task = self._task
            self._stop_event.set()
            self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run(self, **kwargs: object) -> None:
        try:
            if self.animation_type is AnimationType.IDLE:
                await self._run_idle_loop()
                return
            await self.execute(**kwargs)
        except Exception:
            logger.exception("动画控制器 {} 运行失败", self.name)
        finally:
            self._stop_event.set()

    async def _run_idle_loop(self) -> None:
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                await self.run_cycle()
                consecutive_failures = 0
            except Exception:
                consecutive_failures += 1
                logger.exception("动画控制器 {} 循环周期运行失败", self.name)
                # 退避，避免 run_cycle 在首个 await 前同步抛错时陷入 100% CPU 紧自旋
                await asyncio.sleep(min(1.0, 0.1 * consecutive_failures))

    async def run_cycle(self) -> None:
        """执行一个循环周期，仅循环控制器需要实现"""

        raise NotImplementedError(f"控制器 {self.name} 未实现循环周期")

    async def execute(self, **kwargs: object) -> None:
        """执行一次动画，仅一次性控制器需要实现"""

        _ = kwargs
        raise NotImplementedError(f"控制器 {self.name} 未实现一次性动画")

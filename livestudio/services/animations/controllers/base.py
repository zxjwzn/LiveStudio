"""动画控制器抽象。"""

from __future__ import annotations

import asyncio
import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

from livestudio.log import logger

from ..config import ControllerSettings
from ..models import AnimationType

ConfigT = TypeVar("ConfigT", bound=ControllerSettings)


class AnimationController(ABC, Generic[ConfigT]):
    """动画控制器统一抽象。"""

    def __init__(
        self,
        # runtime: AnimationRuntimeService,
        name: str,
        config: ConfigT,
    ) -> None:
        # self._runtime = runtime
        self._name = name
        self._config = config
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    # @property
    # def runtime(self) -> AnimationRuntimeService:
    #    return self._runtime

    @property
    def name(self) -> str:
        return self._name

    @property
    def config(self) -> ConfigT:
        return self._config

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    @abstractmethod
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

    async def start(self, **kwargs: object) -> bool:
        if not self.enabled:
            logger.info("动画控制器 {} 未启用，跳过启动", self.name)
            return False
        if self.is_running:
            logger.debug("动画控制器 {} 已在运行", self.name)
            return False
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(**kwargs))
        return True

    async def stop(self) -> None:
        task = self._task
        self._stop_event.set()
        self._task = None
        if task is not None:
            await task

    async def stop_without_wait(self) -> None:
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
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("动画控制器 {} 运行失败", self.name)
        finally:
            self._stop_event.set()

    async def _run_idle_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.run_cycle()

    @abstractmethod
    async def run_cycle(self) -> None:
        """执行一个循环周期，仅循环控制器需要实现。"""

    @abstractmethod
    async def execute(self, **kwargs: object) -> None:
        """执行一次动画，仅一次性控制器需要实现。"""

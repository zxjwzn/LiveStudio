"""参数缓动引擎。"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Literal

from livestudio.log import logger

from .easing import EASING_REGISTRY, Easing, EasingFunction
from .models import ActiveTween, ControlledParameterState, TweenRequest

ParameterSender = Callable[
    [Iterable[ControlledParameterState], Literal["set", "add"]],
    Awaitable[None],
]


class ParameterTweenEngine:
    """以确定性的缓动时序驱动参数值变化。"""

    def __init__(
        self,
        sender: ParameterSender,
        *,
        keep_alive_interval: float = 0.5,
        default_fps: int = 60,
    ) -> None:
        self._sender = sender
        self._keep_alive_interval = keep_alive_interval
        self._default_fps = default_fps
        self._lock = asyncio.Lock()
        self._controlled_params: dict[str, ControlledParameterState] = {}
        self._active_tweens: dict[str, ActiveTween] = {}
        self._keep_alive_task: asyncio.Task[None] | None = None

    @property
    def controlled_params(self) -> dict[str, ControlledParameterState]:
        """返回当前受控参数"""

        return dict(self._controlled_params)

    @property
    def active_parameters(self) -> tuple[str, ...]:
        """返回当前存在活动缓动的参数名。"""

        return tuple(self._active_tweens)

    @property
    def is_running(self) -> bool:
        """保活循环当前是否处于活动状态"""

        return self._keep_alive_task is not None and not self._keep_alive_task.done()

    def start(self) -> None:
        """启动保活循环"""

        if self.is_running:
            logger.warning("缓动引擎保活任务已在运行")
            return
        self._keep_alive_task = asyncio.create_task(self._keep_alive_loop())
        logger.info("缓动引擎已启动")

    async def stop(self) -> None:
        """停止保活，并取消所有活动中的缓动任务。"""

        task = self._keep_alive_task
        self._keep_alive_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        async with self._lock:
            active_tasks = [active.task for active in self._active_tweens.values()]
            self._active_tweens.clear()
            self._controlled_params.clear()

        for active_task in active_tasks:
            active_task.cancel()

        for active_task in active_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await active_task

        logger.info("缓动引擎已停止")

    async def restart(self) -> None:
        """重启缓动引擎。"""

        await self.stop()
        self.start()

    async def tween(self, request: TweenRequest) -> None:
        """按请求使用固定采样与绝对时间对齐方式执行缓动。"""

        if request.fps <= 0:
            request.fps = self._default_fps
        task = asyncio.create_task(self._run_tween(request))
        await task

    async def release(self, parameter_name: str) -> None:
        """释放某个参数的控制权，并在需要时取消其缓动任务。"""

        task_to_cancel: asyncio.Task[None] | None = None
        async with self._lock:
            self._controlled_params.pop(parameter_name, None)
            active = self._active_tweens.pop(parameter_name, None)
            if active is not None:
                task_to_cancel = active.task

        if task_to_cancel is not None:
            task_to_cancel.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task_to_cancel

    async def release_many(self, parameter_names: Iterable[str]) -> None:
        """释放多个参数的控制权。"""

        for parameter_name in tuple(parameter_names):
            await self.release(parameter_name)

    async def cancel(self, parameter_name: str, *, release: bool = False) -> None:
        """取消某个参数的活动缓动，并可选择是否释放控制权。"""

        task_to_cancel: asyncio.Task[None] | None = None
        async with self._lock:
            active = self._active_tweens.pop(parameter_name, None)
            if active is not None:
                task_to_cancel = active.task
            if release:
                self._controlled_params.pop(parameter_name, None)

        if task_to_cancel is not None:
            task_to_cancel.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task_to_cancel

    async def cancel_all(self) -> None:
        """取消所有活动缓动，并保留各参数最后一次已发送的值。"""

        async with self._lock:
            active_tweens = tuple(self._active_tweens.values())
            self._active_tweens.clear()

        for active in active_tweens:
            active.task.cancel()

        for active in active_tweens:
            with contextlib.suppress(asyncio.CancelledError):
                await active.task

    async def release_all(self) -> None:
        """释放所有受控参数。"""

        async with self._lock:
            parameter_names = tuple(self._controlled_params.keys())

        for parameter_name in parameter_names:
            await self.release(parameter_name)

    def _resolve_easing(self, easing: str | EasingFunction) -> EasingFunction:
        if callable(easing):
            return easing
        if easing not in EASING_REGISTRY:
            raise ValueError(f"未知缓动函数: {easing}")
        return EASING_REGISTRY[easing]

    async def _run_tween(self, request: TweenRequest) -> None:
        current_task = asyncio.current_task()
        if current_task is None:
            logger.error("无法获取当前缓动任务")
            return

        if request.delay > 0:
            await asyncio.sleep(request.delay)

        if request.start_value is None:
            async with self._lock:
                current_state = self._controlled_params.get(request.parameter_name)
                start_value = current_state.value if current_state is not None else 0.0
        else:
            start_value = request.start_value

        if request.duration <= 0 or start_value == request.end_value:
            await self._apply_immediate_value(current_task, request, start_value)
            return

        loop = asyncio.get_running_loop()
        start_time = loop.time()
        steps = max(1, int(request.duration * request.fps))
        interval = request.duration / steps

        async with self._lock:
            existing = self._active_tweens.get(request.parameter_name)
            if existing is not None and request.priority <= existing.priority:
                logger.debug(
                    "参数 {} 的缓动被拒绝，当前优先级 {} >= 新优先级 {}",
                    request.parameter_name,
                    existing.priority,
                    request.priority,
                )
                return
            self._active_tweens[request.parameter_name] = ActiveTween(
                task=current_task,
                priority=request.priority,
                mode=request.mode,
                keep_alive=request.keep_alive,
            )

        try:
            for step in range(steps):
                target_time = start_time + (step + 1) * interval
                now = loop.time()
                sleep_time = target_time - now
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                elapsed = min(request.duration, max(0.0, loop.time() - start_time))
                t = min(1.0, elapsed / request.duration)
                value = start_value + (
                    request.end_value - start_value
                ) * self._resolve_easing(request.easing)(t)
                should_send = False

                async with self._lock:
                    active = self._active_tweens.get(request.parameter_name)
                    if active is not None and active.task is current_task:
                        self._controlled_params[request.parameter_name] = (
                            ControlledParameterState(
                                name=request.parameter_name,
                                value=value,
                                mode=request.mode,
                                keep_alive=request.keep_alive,
                            )
                        )
                        should_send = True

                if should_send:
                    await self._send_parameter_values(
                        [
                            ControlledParameterState(
                                name=request.parameter_name,
                                value=value,
                                mode=request.mode,
                                keep_alive=request.keep_alive,
                            ),
                        ],
                    )
        except asyncio.CancelledError:
            logger.debug("参数 {} 的缓动任务被取消", request.parameter_name)
            raise
        finally:
            async with self._lock:
                active = self._active_tweens.get(request.parameter_name)
                if active is not None and active.task is current_task:
                    del self._active_tweens[request.parameter_name]

    async def _apply_immediate_value(
        self,
        current_task: asyncio.Task[None],
        request: TweenRequest,
        start_value: float,
    ) -> None:
        _ = start_value
        async with self._lock:
            existing = self._active_tweens.get(request.parameter_name)
            if existing is not None and request.priority <= existing.priority:
                logger.debug(
                    "参数 {} 的即时设置被拒绝，当前优先级 {} >= 新优先级 {}",
                    request.parameter_name,
                    existing.priority,
                    request.priority,
                )
                return

            self._active_tweens[request.parameter_name] = ActiveTween(
                task=current_task,
                priority=request.priority,
                mode=request.mode,
                keep_alive=request.keep_alive,
            )
            self._controlled_params[request.parameter_name] = ControlledParameterState(
                name=request.parameter_name,
                value=request.end_value,
                mode=request.mode,
                keep_alive=request.keep_alive,
            )

        try:
            await self._send_parameter_values(
                [self._controlled_params[request.parameter_name]],
            )
        finally:
            async with self._lock:
                active = self._active_tweens.get(request.parameter_name)
                if active is not None and active.task is current_task:
                    del self._active_tweens[request.parameter_name]

    async def _keep_alive_loop(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            start_time = loop.time()
            tick = 0
            while True:
                tick += 1
                next_time = start_time + tick * self._keep_alive_interval
                sleep_time = next_time - loop.time()
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

                async with self._lock:
                    states_to_send = [
                        state
                        for parameter_name, state in self._controlled_params.items()
                        if state.keep_alive
                        and parameter_name not in self._active_tweens
                    ]

                if not states_to_send:
                    continue

                await self._send_parameter_values(states_to_send)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("缓动引擎保活循环出错")

    async def _send_parameter_values(
        self,
        states: Iterable[ControlledParameterState],
    ) -> None:
        parameter_states = list(states)
        if not parameter_states:
            return
        await self._sender(parameter_states, parameter_states[0].mode)

"""参数缓动引擎"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterable
from typing import Literal

from livestudio.utils.log import logger

from .easing import EASING_REGISTRY, EasingFunction
from .models import ActiveTween, ControlledParameterState, TweenRequest

ParameterSender = Callable[
    [Iterable[ControlledParameterState], Literal["set", "add"]],
    Awaitable[None],
]


class ParameterTweenEngine:
    """以确定性的缓动时序驱动参数值变化"""

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
        """返回当前存在活动缓动的参数名"""

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
        """停止保活，并取消所有活动中的缓动任务"""

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
        """重启缓动引擎"""

        await self.stop()
        self.start()

    async def tween(self, request: TweenRequest) -> None:
        """按请求使用固定采样与绝对时间对齐方式执行缓动"""

        if request.fps <= 0:
            request.fps = self._default_fps
        # 让 _run_tween 能通过 asyncio.current_task() 获取自身引用。
        task = asyncio.create_task(self._run_tween(request))
        await task

    async def release(self, parameter_name: str) -> None:
        """释放某个参数的控制权，并在需要时取消其缓动任务"""

        await self.cancel(parameter_name, release=True)

    async def release_many(self, parameter_names: Iterable[str]) -> None:
        """释放多个参数的控制权"""

        for parameter_name in tuple(parameter_names):
            await self.release(parameter_name)

    async def cancel(self, parameter_name: str, *, release: bool = False) -> None:
        """取消某个参数的活动缓动，并可选择是否释放控制权"""

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
        """取消所有活动缓动，并保留各参数最后一次已发送的值"""

        async with self._lock:
            active_tweens = tuple(self._active_tweens.values())
            self._active_tweens.clear()

        for active in active_tweens:
            active.task.cancel()

        for active in active_tweens:
            with contextlib.suppress(asyncio.CancelledError):
                await active.task

    async def release_all(self) -> None:
        """释放所有受控参数"""

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

    def _try_acquire(
        self,
        current_task: asyncio.Task[None],
        request: TweenRequest,
        *,
        context: str = "缓动",
    ) -> bool:
        """在持有 _lock 的前提下，尝试获取参数的缓动控制权

        如果当前已有更高或相同优先级的缓动占用该参数，则拒绝并返回 False。
        否则注册新的 ActiveTween 并返回 True。
        """

        existing = self._active_tweens.get(request.parameter_name)
        if existing is not None and request.priority <= existing.priority:
            logger.debug(
                "参数 {} 的{}被拒绝，当前优先级 {} >= 新优先级 {}",
                request.parameter_name,
                context,
                existing.priority,
                request.priority,
            )
            return False
        self._active_tweens[request.parameter_name] = ActiveTween(
            task=current_task,
            priority=request.priority,
            mode=request.mode,
            keep_alive=request.keep_alive,
        )
        return True

    def _release_active(
        self,
        current_task: asyncio.Task[None],
        parameter_name: str,
    ) -> None:
        """在持有 _lock 的前提下，释放当前任务对参数的缓动控制权"""

        active = self._active_tweens.get(parameter_name)
        if active is not None and active.task is current_task:
            del self._active_tweens[parameter_name]

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
            await self._apply_immediate_value(current_task, request)
            return

        loop = asyncio.get_running_loop()
        start_time = loop.time()
        steps = max(1, int(request.duration * request.fps))
        interval = request.duration / steps

        async with self._lock:
            if not self._try_acquire(current_task, request, context="缓动"):
                return

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
                state_to_send: ControlledParameterState | None = None

                async with self._lock:
                    active = self._active_tweens.get(request.parameter_name)
                    if active is not None and active.task is current_task:
                        state_to_send = ControlledParameterState(
                            name=request.parameter_name,
                            value=value,
                            mode=request.mode,
                            keep_alive=request.keep_alive,
                        )
                        self._controlled_params[request.parameter_name] = state_to_send

                if state_to_send is not None:
                    await self._send_parameter_values([state_to_send])
        except asyncio.CancelledError:
            logger.debug("参数 {} 的缓动任务被取消", request.parameter_name)
            raise
        finally:
            async with self._lock:
                self._release_active(current_task, request.parameter_name)

    async def _apply_immediate_value(
        self,
        current_task: asyncio.Task[None],
        request: TweenRequest,
    ) -> None:
        async with self._lock:
            if not self._try_acquire(current_task, request, context="即时设置"):
                return

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
                self._release_active(current_task, request.parameter_name)

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
        except Exception:
            logger.exception("缓动引擎保活循环出错")

    async def _send_parameter_values(
        self,
        states: Iterable[ControlledParameterState],
    ) -> None:
        parameter_states = list(states)
        if not parameter_states:
            return
        set_states = [state for state in parameter_states if state.mode == "set"]
        add_states = [state for state in parameter_states if state.mode == "add"]
        if set_states:
            await self._sender(set_states, "set")
        if add_states:
            await self._sender(add_states, "add")

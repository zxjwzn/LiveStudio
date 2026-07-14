"""Performance 纯调度内核：草稿、FIFO 队列、锚点与事件通知。"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import math
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from livestudio.utils.log import logger

from .models import (
    AnchorPhase,
    DraftSnapshot,
    EnqueueResult,
    EventRuntime,
    EventStatus,
    EventType,
    JobSnapshot,
    JobState,
    PerformanceEvent,
    QueueSnapshot,
    RemoveJobResult,
    StartRef,
    TimelineEvent,
)

_FINISHED_LIMIT = 20

PerformanceEventListener = Callable[[PerformanceEvent], Awaitable[None] | None]
Handler = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class _Job:
    job_id: str
    enqueue_delay: float
    events: list[TimelineEvent]
    state: JobState = JobState.PENDING
    phase: str | None = None
    error: str | None = None
    runtimes: dict[str, EventRuntime] = field(default_factory=dict)
    anchors: dict[tuple[str, AnchorPhase], float] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        if self.runtimes:
            return
        self.runtimes = {
            event.id: EventRuntime(
                id=event.id,
                type=event.type,
                name=event.name,
                payload=dict(event.payload),
                start=event.start.model_copy(deep=True),
                end=event.end.model_copy(deep=True) if event.end is not None else None,
            )
            for event in self.events
        }

    def snapshot(self) -> JobSnapshot:
        return JobSnapshot(
            job_id=self.job_id,
            state=self.state,
            enqueue_delay=self.enqueue_delay,
            events=list(self.runtimes.values()),
            phase=self.phase,
            error=self.error,
        )


class PerformanceService:
    """只负责事件时间关系与队列状态，不执行任何业务能力。"""

    def __init__(self) -> None:
        self._draft: list[TimelineEvent] = []
        self._id_counter = itertools.count(1)
        self._job_counter = itertools.count(1)
        self._running: _Job | None = None
        self._pending: list[_Job] = []
        self._finished: list[JobSnapshot] = []
        self._listeners: list[PerformanceEventListener] = []
        self._handlers: dict[str, Handler] = {}
        self._lock = asyncio.Lock()

    def subscribe(self, listener: PerformanceEventListener) -> Callable[[], None]:
        """订阅事件开始与结束通知，返回取消订阅函数。"""

        if listener not in self._listeners:
            self._listeners.append(listener)

        def _unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._listeners.remove(listener)

        return _unsubscribe

    def register_handler(self, name: str, handler: Handler) -> Callable[[], None]:
        """注册动作处理器:命中事件 name 时,调度器在 START 与 END 之间 await handler(payload)。

        handler 返回即该事件的 END(自然结束),适用于自终止、时长未知的动作;handler 体
        无需感知 Performance。handler 抛异常 -> 事件 FAILED(仍补 END 锚,避免依赖方卡死);
        Job 取消 -> handler 被取消、事件 CANCELLED。若事件同时声明了 end_anchor,handler
        优先生效(end_anchor 被忽略)。重复注册同名 handler 会覆盖旧值。返回取消注册函数。
        """

        key = name.strip() if isinstance(name, str) else ""
        if not key:
            raise ValueError("handler name 不能为空")
        self._handlers[key] = handler

        def _unregister() -> None:
            self._handlers.pop(key, None)

        return _unregister

    def add_event(
        self,
        name: str,
        payload: Mapping[str, Any] | None = None,
        *,
        event_id: str | None = None,
        start_anchor: str = "group",
        start_phase: str | AnchorPhase = AnchorPhase.START,
        delay: float = 0.0,
        end_anchor: str | None = None,
        end_phase: str | AnchorPhase = AnchorPhase.END,
        end_delay: float = 0.0,
    ) -> DraftSnapshot:
        """向草稿添加通用调度事件。"""

        if not isinstance(name, str) or not name.strip():
            return self._draft_error("事件 name 不能为空")
        return self._add_timeline_event(
            event_type=EventType.EVENT,
            name=name.strip(),
            payload=dict(payload or {}),
            event_id=event_id,
            start_anchor=start_anchor,
            start_phase=start_phase,
            delay=delay,
            end_anchor=end_anchor,
            end_phase=end_phase,
            end_delay=end_delay,
        )

    def add_wait_event(
        self,
        seconds: float,
        *,
        event_id: str | None = None,
        start_anchor: str = "group",
        start_phase: str | AnchorPhase = AnchorPhase.START,
        delay: float = 0.0,
    ) -> DraftSnapshot:
        """向草稿添加调度器内置等待事件。"""

        try:
            duration = float(seconds)
        except (TypeError, ValueError) as exc:
            return self._draft_error("wait.seconds 须为数字", exc)
        if not math.isfinite(duration) or duration < 0:
            return self._draft_error("wait.seconds 须为有限的非负数")
        return self._add_timeline_event(
            event_type=EventType.WAIT,
            name=None,
            payload={"seconds": duration},
            event_id=event_id,
            start_anchor=start_anchor,
            start_phase=start_phase,
            delay=delay,
            end_anchor=None,
            end_phase=AnchorPhase.END,
            end_delay=0.0,
        )

    def _add_timeline_event(
        self,
        *,
        event_type: EventType,
        name: str | None,
        payload: dict[str, Any],
        event_id: str | None,
        start_anchor: str,
        start_phase: str | AnchorPhase,
        delay: float,
        end_anchor: str | None,
        end_phase: str | AnchorPhase,
        end_delay: float,
    ) -> DraftSnapshot:
        try:
            start_p = start_phase if isinstance(start_phase, AnchorPhase) else AnchorPhase(start_phase)
            end_p = end_phase if isinstance(end_phase, AnchorPhase) else AnchorPhase(end_phase)
        except ValueError as exc:
            return self._draft_error(f"未知锚点 phase: {exc}", exc)
        if not _valid_delay(delay) or not _valid_delay(end_delay):
            return self._draft_error("delay 与 end_delay 须为有限的非负数")

        resolved_id = event_id.strip() if isinstance(event_id, str) and event_id.strip() else f"e{next(self._id_counter)}"
        if any(event.id == resolved_id for event in self._draft):
            return self._draft_error(f"事件 id 已存在: {resolved_id}")

        start_a = (start_anchor or "group").strip() or "group"
        if start_a == resolved_id:
            return self._draft_error("start_anchor 不能指向事件自身")
        if start_a != "group" and not any(event.id == start_a for event in self._draft):
            return self._draft_error(f"start_anchor '{start_a}' 不在当前事件组")
        if start_a == "group" and start_p is AnchorPhase.END:
            return self._draft_error("事件不能依赖 group.end")

        end_ref: StartRef | None = None
        if end_anchor is not None and end_anchor.strip():
            end_a = end_anchor.strip()
            if end_a == resolved_id:
                return self._draft_error("end_anchor 不能指向事件自身")
            if end_a != "group" and not any(event.id == end_a for event in self._draft):
                return self._draft_error(f"end_anchor '{end_a}' 不在当前事件组")
            if end_a == "group" and end_p is AnchorPhase.END:
                return self._draft_error("事件不能依赖 group.end")
            end_ref = StartRef(anchor=end_a, phase=end_p, delay=float(end_delay))

        event = TimelineEvent(
            id=resolved_id,
            type=event_type,
            name=name,
            payload=payload,
            start=StartRef(anchor=start_a, phase=start_p, delay=float(delay)),
            end=end_ref,
        )
        cycle = _find_cycle([*self._draft, event])
        if cycle is not None:
            return self._draft_error(f"事件依赖成环: {' -> '.join(cycle)}")
        self._draft.append(event)
        return self.get_draft()

    def remove_event(self, event_id: str) -> DraftSnapshot:
        """删除未被其他事件引用的草稿事件。"""

        if not any(event.id == event_id for event in self._draft):
            return self._draft_error(f"草稿中无事件: {event_id}")
        dependents = [
            event.id
            for event in self._draft
            if event.id != event_id
            and (event.start.anchor == event_id or (event.end is not None and event.end.anchor == event_id))
        ]
        if dependents:
            return self._draft_error(f"事件 {event_id} 仍被 {', '.join(dependents)} 引用,请先删除依赖方")
        self._draft = [event for event in self._draft if event.id != event_id]
        return self.get_draft()

    def get_draft(self) -> DraftSnapshot:
        errors = _validate_graph(self._draft)
        return DraftSnapshot(events=list(self._draft), valid=not errors, errors=errors)

    def clear_draft(self) -> DraftSnapshot:
        self._draft.clear()
        return self.get_draft()

    async def enqueue_draft(self, delay: float = 0.0) -> EnqueueResult:
        """校验草稿、快照入队并清空草稿。"""

        if not _valid_delay(delay):
            return EnqueueResult(
                ok=False,
                error="invalid_delay",
                message="delay 须为有限的非负数",
                draft=self.get_draft(),
            )
        draft = self.get_draft()
        if not draft.events:
            return EnqueueResult(ok=False, error="empty_draft", message="当前事件组为空", draft=draft)
        if not draft.valid:
            return EnqueueResult(
                ok=False,
                error="invalid_draft",
                message="; ".join(draft.errors),
                draft=draft,
            )

        job = _Job(
            job_id=f"job_{next(self._job_counter)}",
            enqueue_delay=float(delay),
            events=[event.model_copy(deep=True) for event in self._draft],
        )
        self._draft.clear()
        async with self._lock:
            if self._running is None:
                self._running = job
                job.state = JobState.RUNNING
                job.task = asyncio.create_task(self._run_job(job))
                position = 0
            else:
                self._pending.append(job)
                position = len(self._pending)
        return EnqueueResult(
            ok=True,
            job_id=job.job_id,
            state=job.state,
            position=position,
            queue_size=(1 if self._running else 0) + len(self._pending),
            start_delay=job.enqueue_delay,
            draft=self.get_draft(),
            queue=self.list_jobs(),
        )

    def list_jobs(self, *, include_finished: bool = False, limit: int = 20) -> QueueSnapshot:
        finished = list(self._finished[-limit:]) if include_finished and limit > 0 else []
        return QueueSnapshot(
            running=self._running.snapshot() if self._running is not None else None,
            pending=[job.snapshot() for job in self._pending],
            finished=finished,
        )

    def get_job(self, job_id: str) -> JobSnapshot | None:
        if self._running is not None and self._running.job_id == job_id:
            return self._running.snapshot()
        for job in self._pending:
            if job.job_id == job_id:
                return job.snapshot()
        for snapshot in reversed(self._finished):
            if snapshot.job_id == job_id:
                return snapshot
        return None

    async def remove_job(self, job_id: str | None = None, *, clear_all: bool = False) -> RemoveJobResult:
        """删除等待任务或取消运行任务。"""

        removed: list[str] = []
        to_cancel: _Job | None = None
        pending_to_drop: list[_Job] = []
        async with self._lock:
            if clear_all:
                to_cancel = self._running
                self._running = None
                pending_to_drop = list(self._pending)
                self._pending.clear()
            elif job_id is None:
                return RemoveJobResult(ok=False, message="须提供 job_id 或 clear_all=true", queue=self.list_jobs())
            else:
                for index, job in enumerate(self._pending):
                    if job.job_id != job_id:
                        continue
                    self._pending.pop(index)
                    job.state = JobState.CANCELLED
                    removed.append(job_id)
                    self._push_finished(job.snapshot())
                    return RemoveJobResult(ok=True, removed=removed, queue=self.list_jobs())
                if self._running is not None and self._running.job_id == job_id:
                    to_cancel = self._running
                    self._running = None
                else:
                    return RemoveJobResult(ok=False, message=f"未找到 job: {job_id}", queue=self.list_jobs())

        cancelled_running = to_cancel is not None
        if to_cancel is not None:
            removed.append(to_cancel.job_id)
            await self._cancel_job(to_cancel)
            if to_cancel.state not in (JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED):
                self._finish(to_cancel, JobState.CANCELLED)
        for job in pending_to_drop:
            job.state = JobState.CANCELLED
            removed.append(job.job_id)
            self._push_finished(job.snapshot())
        async with self._lock:
            if self._running is None and not clear_all:
                await self._kick_next_unlocked()
        return RemoveJobResult(
            ok=True,
            removed=removed,
            cancelled_running=cancelled_running,
            queue=self.list_jobs(),
        )

    def summary_line(self) -> str:
        draft_names = ",".join(event.name or event.type.value for event in self._draft) or "-"
        if self._running is None:
            running = "none"
        else:
            statuses = ",".join(f"{item.id}:{item.status.value}" for item in self._running.runtimes.values())
            running = f"{self._running.job_id}[{self._running.phase or self._running.state.value}|{statuses}]"
        return f"draft:{len(self._draft)}({draft_names}); running={running}; pending={len(self._pending)}"

    async def shutdown(self) -> None:
        await self.remove_job(clear_all=True)

    async def _run_job(self, job: _Job) -> None:
        try:
            if job.enqueue_delay > 0:
                job.phase = "starting_delay"
                await _wait_or_cancel(job.enqueue_delay, job.cancel_event)
            if job.cancel_event.is_set():
                self._finish(job, JobState.CANCELLED)
                return
            job.phase = "playing"
            job.anchors[("group", AnchorPhase.START)] = time.perf_counter()
            tasks = [
                asyncio.create_task(self._run_event(job, event), name=f"perf-{job.job_id}-{event.id}") for event in job.events
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if job.cancel_event.is_set():
                state = JobState.CANCELLED
            elif any(runtime.status is EventStatus.FAILED for runtime in job.runtimes.values()):
                state = JobState.FAILED
                job.error = "one or more events failed"
            else:
                state = JobState.COMPLETED
            for result in results:
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.opt(exception=result).error("Performance 事件任务异常: {}", result)
            job.anchors[("group", AnchorPhase.END)] = time.perf_counter()
            self._finish(job, state)
        except asyncio.CancelledError:
            self._finish(job, JobState.CANCELLED)
            raise
        except Exception as exc:
            logger.opt(exception=exc).error("Performance Job {} 调度失败", job.job_id)
            job.error = str(exc)
            self._finish(job, JobState.FAILED)
        finally:
            await self._on_job_done(job)

    async def _run_event(self, job: _Job, event: TimelineEvent) -> None:
        runtime = job.runtimes[event.id]
        try:
            fire_at = await self._wait_for_ref(job, event.start)
            wait_more = fire_at - time.perf_counter()
            if wait_more > 0:
                runtime.status = EventStatus.ARMED
                await _wait_or_cancel(wait_more, job.cancel_event)
            if job.cancel_event.is_set():
                runtime.status = EventStatus.CANCELLED
                return
            runtime.status = EventStatus.RUNNING
            await self._schedule_event(job, event, runtime)
        except asyncio.CancelledError:
            runtime.status = EventStatus.CANCELLED
            await self._close_event(job, event, runtime)
            raise
        except Exception as exc:
            runtime.status = EventStatus.FAILED
            runtime.error = str(exc)
            logger.opt(exception=exc).error("Performance 事件 {} 调度失败", event.id)
            await self._close_event(job, event, runtime)

    async def _schedule_event(self, job: _Job, event: TimelineEvent, runtime: EventRuntime) -> None:
        started_at = time.perf_counter()
        runtime.t_start = started_at
        self._mark_anchor(job, event.id, AnchorPhase.START, started_at)
        await self._emit(job, event, AnchorPhase.START, started_at)

        if event.type is EventType.WAIT:
            await _wait_or_cancel(float(event.payload["seconds"]), job.cancel_event)
        elif event.name is not None and event.name in self._handlers:
            handler = self._handlers[event.name]
            await _await_or_cancel(handler(dict(event.payload)), job.cancel_event)
        elif event.end is not None:
            fire_at = await self._wait_for_ref(job, event.end)
            wait_more = fire_at - time.perf_counter()
            if wait_more > 0:
                await _wait_or_cancel(wait_more, job.cancel_event)

        if job.cancel_event.is_set():
            runtime.status = EventStatus.CANCELLED
        else:
            runtime.status = EventStatus.COMPLETED
        await self._close_event(job, event, runtime)

    async def _close_event(self, job: _Job, event: TimelineEvent, runtime: EventRuntime) -> None:
        if (event.id, AnchorPhase.START) not in job.anchors:
            return
        if (event.id, AnchorPhase.END) in job.anchors:
            return
        ended_at = time.perf_counter()
        runtime.t_end = ended_at
        self._mark_anchor(job, event.id, AnchorPhase.END, ended_at)
        await self._emit(job, event, AnchorPhase.END, ended_at)

    async def _emit(self, job: _Job, event: TimelineEvent, phase: AnchorPhase, timestamp: float) -> None:
        notification = PerformanceEvent(
            job_id=job.job_id,
            event_id=event.id,
            type=event.type,
            name=event.name,
            payload=dict(event.payload),
            phase=phase,
            timestamp=timestamp,
        )
        for listener in tuple(self._listeners):
            try:
                result = listener(notification)
                if isinstance(result, Awaitable):
                    await result
            except Exception:
                logger.exception("Performance 事件监听器执行失败")

    async def _wait_for_ref(self, job: _Job, ref: StartRef) -> float:
        key = (ref.anchor, ref.phase)
        while key not in job.anchors:
            if job.cancel_event.is_set():
                raise asyncio.CancelledError
            await asyncio.sleep(0.01)
        return job.anchors[key] + ref.delay

    def _mark_anchor(self, job: _Job, event_id: str, phase: AnchorPhase, timestamp: float) -> None:
        job.anchors.setdefault((event_id, phase), timestamp)

    async def _cancel_job(self, job: _Job) -> None:
        job.cancel_event.set()
        task = job.task
        if task is None or task.done() or task is asyncio.current_task():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def _finish(self, job: _Job, state: JobState) -> None:
        if job.state in (JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED):
            return
        job.state = state
        job.phase = None
        self._push_finished(job.snapshot())

    def _push_finished(self, snapshot: JobSnapshot) -> None:
        self._finished.append(snapshot)
        if len(self._finished) > _FINISHED_LIMIT:
            self._finished = self._finished[-_FINISHED_LIMIT:]

    async def _on_job_done(self, job: _Job) -> None:
        async with self._lock:
            if self._running is job:
                self._running = None
            await self._kick_next_unlocked()

    async def _kick_next_unlocked(self) -> None:
        if self._running is not None or not self._pending:
            return
        next_job = self._pending.pop(0)
        self._running = next_job
        next_job.state = JobState.RUNNING
        next_job.task = asyncio.create_task(self._run_job(next_job))

    def _draft_error(self, message: str, _exc: BaseException | None = None) -> DraftSnapshot:
        current = self.get_draft()
        return DraftSnapshot(events=current.events, valid=False, errors=[*current.errors, message])


def _valid_delay(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    resolved = float(value)
    return math.isfinite(resolved) and resolved >= 0


async def _wait_or_cancel(seconds: float, cancel_event: asyncio.Event) -> None:
    if seconds <= 0:
        return
    deadline = time.perf_counter() + seconds
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return
        try:
            await asyncio.wait_for(cancel_event.wait(), timeout=remaining)
            raise asyncio.CancelledError
        except TimeoutError:
            continue


async def _await_or_cancel(awaitable: Awaitable[None], cancel_event: asyncio.Event) -> None:
    """Await a registered handler; raise CancelledError if cancel_event fires first.

    handler 的异常会原样抛出(由 _run_event 映射为 FAILED)。cancel_event 先到则取消
    handler 并抛 CancelledError(由 _run_event 映射为 CANCELLED)。任一出口都取消并收尾
    残留的 Future,避免 task 泄漏与 "destroyed while pending" 告警。
    """

    task: asyncio.Task[None] = asyncio.ensure_future(awaitable)
    wait_task: asyncio.Task[bool] = asyncio.ensure_future(cancel_event.wait())
    try:
        done, _ = await asyncio.wait({task, wait_task}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        await _abort(wait_task)
        await _abort(task)
        raise
    await _abort(wait_task)
    if task in done:
        # 自然完成(或抛异常):交由 result() 抛出,沿用 _run_event 的 FAILED/COMPLETED 路径
        _ = task.result()
        return
    await _abort(task)
    raise asyncio.CancelledError


async def _abort(fut: asyncio.Future[Any]) -> None:
    """取消并收尾一个 Future;丢弃其收尾异常(仅用于正在放弃的句柄)。"""

    if not fut.done():
        fut.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await fut


def _validate_graph(events: list[TimelineEvent]) -> list[str]:
    errors: list[str] = []
    ids = [event.id for event in events]
    if len(set(ids)) != len(ids):
        errors.append("事件 id 不能重复")
    known = set(ids)
    for event in events:
        if event.type is EventType.EVENT and (not isinstance(event.name, str) or not event.name.strip()):
            errors.append(f"{event.id}: event.name 不能为空")
        if event.type is EventType.WAIT:
            seconds = event.payload.get("seconds")
            if not _valid_delay(seconds):
                errors.append(f"{event.id}: wait.seconds 须为有限的非负数")
        for label, ref in (("start", event.start), ("end", event.end)):
            if ref is None:
                continue
            if ref.anchor == event.id:
                errors.append(f"{event.id}: {label}_anchor 不能指向自身")
            elif ref.anchor != "group" and ref.anchor not in known:
                errors.append(f"{event.id}: 未知 {label}_anchor '{ref.anchor}'")
            if ref.anchor == "group" and ref.phase is AnchorPhase.END:
                errors.append(f"{event.id}: 不能依赖 group.end")
            if not _valid_delay(ref.delay):
                errors.append(f"{event.id}: {label} delay 须为有限的非负数")
    cycle = _find_cycle(events)
    if cycle is not None:
        errors.append(f"依赖成环: {' -> '.join(cycle)}")
    return errors


def _find_cycle(events: list[TimelineEvent]) -> list[str] | None:
    graph: dict[str, list[str]] = {event.id: [] for event in events}
    for event in events:
        for ref in (event.start, event.end):
            if ref is not None and ref.anchor != "group" and ref.anchor in graph:
                graph[event.id].append(ref.anchor)

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def _visit(node: str) -> list[str] | None:
        if node in visiting:
            index = stack.index(node) if node in stack else 0
            return [*stack[index:], node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for dependency in graph[node]:
            cycle = _visit(dependency)
            if cycle is not None:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for event_id in graph:
        cycle = _visit(event_id)
        if cycle is not None:
            return cycle
    return None

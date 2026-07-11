"""表演时间线服务:草稿事件组 + FIFO Job 队列 + 锚点图调度

契约摘要:
- 唯一添加入口 add_event(写入草稿);enqueue_draft(delay) 快照入队
- Job 串行:不覆盖 running;remove_job 取消/删除
- 时间模型为相对锚点 + 运行期回填,不预编译 TTS 总时长
- speak.end = 呈现结束(由 host 回报),不是 HTTP 断开
- 通用 end 约束:到点 force-release;事件 end 由能力锚点回报
  恢复/回落可在事件 completed 之后后台继续(不阻塞 Job)
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

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
    QueueSnapshot,
    RemoveJobResult,
    StartRef,
    TimelineEvent,
    validate_event_params,
)

# 已结束 Job 环形缓冲上限
_FINISHED_LIMIT = 20


class PerformanceHost(Protocol):
    """底层表演能力 + 锚点订阅(由 app 实现)。"""

    async def launch_speak(self, text: str) -> None:
        """启动 TTS(不阻塞到播完)。"""
        ...

    async def stop_speak(self) -> None:
        """停止 TTS(幂等)。"""
        ...

    async def launch_play_emotion(
        self,
        emotion: str,
        *,
        intensity: float = 1.0,
        transition_duration: float | None = None,
        hold_duration: float | None = None,
    ) -> None:
        """启动表情 oneshot。hold_duration=None 表示保持到被 cancel。"""
        ...

    async def cancel_play_emotion(self) -> None:
        """协作结束表情 hold(幂等)。恢复可在后台继续,不要求 await 完回落。"""
        ...

    async def launch_set_native_expression(self, name: str, active: bool) -> None:
        """瞬时:设置原生表情。"""
        ...

    async def launch_clear_native_expressions(self) -> None:
        """瞬时:清除原生表情。"""
        ...

    def bind_speak_anchors(
        self,
        on_start: Callable[[], None],
        on_end: Callable[[], None],
    ) -> Callable[[], None]:
        """订阅下一次/当前 speak 的 start/end;返回 unbind。"""
        ...

    def bind_emotion_anchors(
        self,
        on_start: Callable[[], None],
        on_end: Callable[[], None],
    ) -> Callable[[], None]:
        """订阅下一次/当前 play_emotion 的 start/end;返回 unbind。"""
        ...


@dataclass
class _Job:
    job_id: str
    enqueue_delay: float
    events: list[TimelineEvent]
    state: JobState = JobState.PENDING
    phase: str | None = None
    error: str | None = None
    runtimes: dict[str, EventRuntime] = field(default_factory=dict)
    # 已解析锚点:(event_id| "group", phase) -> monotonic 时间
    anchors: dict[tuple[str, AnchorPhase], float] = field(default_factory=dict)
    task: asyncio.Task[None] | None = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        if not self.runtimes:
            self.runtimes = {
                event.id: EventRuntime(
                    id=event.id,
                    type=event.type,
                    params=dict(event.params),
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
    """草稿 + 队列 + 调度器。"""

    def __init__(self, host: PerformanceHost) -> None:
        self._host = host
        self._draft: list[TimelineEvent] = []
        self._id_counter = itertools.count(1)
        self._job_counter = itertools.count(1)
        self._running: _Job | None = None
        self._pending: list[_Job] = []
        self._finished: list[JobSnapshot] = []
        self._lock = asyncio.Lock()

    # --- 草稿 ---

    def add_event(
        self,
        event_type: str | EventType,
        params: Mapping[str, Any] | None = None,
        *,
        event_id: str | None = None,
        start_anchor: str = "group",
        start_phase: str | AnchorPhase = AnchorPhase.START,
        delay: float = 0.0,
        end_anchor: str | None = None,
        end_phase: str | AnchorPhase = AnchorPhase.END,
        end_delay: float = 0.0,
    ) -> DraftSnapshot:
        """向当前事件组添加一条事件;可选 end_* 为通用强制结束约束。"""

        try:
            resolved_type = event_type if isinstance(event_type, EventType) else EventType(event_type)
        except ValueError as exc:
            return self._draft_error(f"未知事件类型: {event_type}", exc)

        try:
            phase = start_phase if isinstance(start_phase, AnchorPhase) else AnchorPhase(start_phase)
        except ValueError as exc:
            return self._draft_error(f"未知 start_phase: {start_phase}", exc)

        if delay < 0:
            return self._draft_error("delay 须 >= 0")
        if end_delay < 0:
            return self._draft_error("end_delay 须 >= 0")

        raw_params = dict(params or {})
        try:
            norm_params = validate_event_params(resolved_type, raw_params)
        except (TypeError, ValueError) as exc:
            return self._draft_error(str(exc), exc)

        resolved_id = (
            event_id.strip()
            if isinstance(event_id, str) and event_id.strip()
            else f"e{next(self._id_counter)}"
        )
        if any(event.id == resolved_id for event in self._draft):
            return self._draft_error(f"事件 id 已存在: {resolved_id}")

        anchor = (start_anchor or "group").strip() or "group"
        if anchor != "group" and not any(event.id == anchor for event in self._draft):
            return self._draft_error(f"start_anchor '{anchor}' 不在当前事件组")

        end_ref: StartRef | None = None
        if end_anchor is not None and str(end_anchor).strip():
            end_a = str(end_anchor).strip()
            try:
                end_p = end_phase if isinstance(end_phase, AnchorPhase) else AnchorPhase(end_phase)
            except ValueError as exc:
                return self._draft_error(f"未知 end_phase: {end_phase}", exc)
            if end_a != "group" and end_a != resolved_id and not any(event.id == end_a for event in self._draft):
                return self._draft_error(f"end_anchor '{end_a}' 不在当前事件组")
            if end_a == resolved_id:
                return self._draft_error("end_anchor 不能指向事件自身")
            end_ref = StartRef(anchor=end_a, phase=end_p, delay=float(end_delay))

        event = TimelineEvent(
            id=resolved_id,
            type=resolved_type,
            params=norm_params,
            start=StartRef(anchor=anchor, phase=phase, delay=float(delay)),
            end=end_ref,
        )
        # 环检测:临时加入后检查
        trial = [*self._draft, event]
        cycle = _find_cycle(trial)
        if cycle is not None:
            return self._draft_error(f"事件依赖成环: {' -> '.join(cycle)}")

        self._draft.append(event)
        return self.get_draft()

    def remove_event(self, event_id: str) -> DraftSnapshot:
        """从草稿删除事件;若仍被其它事件引用则拒绝。"""

        if not any(event.id == event_id for event in self._draft):
            return self._draft_error(f"草稿中无事件: {event_id}")

        dependents = [
            event.id
            for event in self._draft
            if event.id != event_id
            and (
                event.start.anchor == event_id
                or (event.end is not None and event.end.anchor == event_id)
            )
        ]
        if dependents:
            return self._draft_error(
                f"事件 {event_id} 仍被 {', '.join(dependents)} 引用,请先删除依赖方",
            )

        self._draft = [event for event in self._draft if event.id != event_id]
        return self.get_draft()

    def get_draft(self) -> DraftSnapshot:
        errors = _validate_graph(self._draft)
        return DraftSnapshot(events=list(self._draft), valid=not errors, errors=errors)

    def clear_draft(self) -> DraftSnapshot:
        self._draft.clear()
        return self.get_draft()

    # --- 队列 ---

    async def enqueue_draft(self, delay: float = 0.0) -> EnqueueResult:
        """校验草稿、快照入队、清空草稿;空闲则立刻开始。"""

        if delay < 0:
            return EnqueueResult(ok=False, error="invalid_delay", message="delay 须 >= 0", draft=self.get_draft())

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

        overlap = _speak_overlap_risk(draft.events)
        if overlap is not None:
            return EnqueueResult(ok=False, error="speak_overlap", message=overlap, draft=draft)

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
        finished = list(self._finished[-max(0, limit) :]) if include_finished else []
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
        for snap in reversed(self._finished):
            if snap.job_id == job_id:
                return snap
        return None

    async def remove_job(self, job_id: str | None = None, *, clear_all: bool = False) -> RemoveJobResult:
        """删除 pending 或取消 running;clear_all=True 清空队列并停当前。

        取消 running 时先在锁外 await 任务结束,避免与 _on_job_done 抢同一把锁死锁。
        """

        removed: list[str] = []
        cancelled_running = False
        to_cancel: _Job | None = None
        cancel_all_running: _Job | None = None
        pending_to_drop: list[_Job] = []

        async with self._lock:
            if clear_all:
                cancel_all_running = self._running
                self._running = None
                pending_to_drop = list(self._pending)
                self._pending.clear()
            elif job_id is None:
                return RemoveJobResult(ok=False, message="须提供 job_id 或 clear_all=true", queue=self.list_jobs())
            else:
                for index, job in enumerate(self._pending):
                    if job.job_id == job_id:
                        self._pending.pop(index)
                        job.state = JobState.CANCELLED
                        removed.append(job_id)
                        self._push_finished(job.snapshot())
                        return RemoveJobResult(
                            ok=True,
                            removed=removed,
                            cancelled_running=False,
                            queue=self.list_jobs(),
                        )
                if self._running is not None and self._running.job_id == job_id:
                    to_cancel = self._running
                    self._running = None
                else:
                    return RemoveJobResult(
                        ok=False,
                        message=f"未找到 job: {job_id}",
                        queue=self.list_jobs(),
                    )

        # 锁外取消,任务 finally 里的 _on_job_done 可安全获取锁
        if clear_all:
            if cancel_all_running is not None:
                removed.append(cancel_all_running.job_id)
                cancelled_running = True
                await self._cancel_job(cancel_all_running)
                if cancel_all_running.state not in (
                    JobState.COMPLETED,
                    JobState.CANCELLED,
                    JobState.FAILED,
                ):
                    self._finish(cancel_all_running, JobState.CANCELLED)
            for job in pending_to_drop:
                job.state = JobState.CANCELLED
                removed.append(job.job_id)
                self._push_finished(job.snapshot())
            # 空队列 clear_all=true 也 ok(幂等)
            return RemoveJobResult(
                ok=True,
                removed=removed,
                cancelled_running=cancelled_running,
                queue=self.list_jobs(include_finished=False),
            )

        if to_cancel is not None:
            removed.append(to_cancel.job_id)
            cancelled_running = True
            await self._cancel_job(to_cancel)
            if to_cancel.state not in (JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED):
                self._finish(to_cancel, JobState.CANCELLED)
            # _on_job_done 可能已 kick;若 running 仍空则再 kick
            async with self._lock:
                if self._running is None:
                    await self._kick_next_unlocked()
            return RemoveJobResult(
                ok=True,
                removed=removed,
                cancelled_running=True,
                queue=self.list_jobs(),
            )

        return RemoveJobResult(ok=False, message="内部状态异常", queue=self.list_jobs())

    def summary_line(self) -> str:
        """供 runtime_context 注入的一行摘要。"""

        draft_n = len(self._draft)
        draft_types = ",".join(event.type.value for event in self._draft) if self._draft else "-"
        running = self._running
        if running is None:
            run_text = "none"
        else:
            statuses = ",".join(
                f"{rt.id}:{rt.status.value}" for rt in running.runtimes.values()
            )
            run_text = f"{running.job_id}[{running.phase or running.state.value}|{statuses}]"
        pending_n = len(self._pending)
        return f"draft:{draft_n}({draft_types}); running={run_text}; pending={pending_n}"

    async def shutdown(self) -> None:
        """停止服务:取消 running、清空 pending。"""

        await self.remove_job(clear_all=True)

    # --- 调度 ---

    async def _run_job(self, job: _Job) -> None:
        try:
            if job.enqueue_delay > 0:
                job.phase = "starting_delay"
                await _wait_or_cancel(job.enqueue_delay, job.cancel_event)
            if job.cancel_event.is_set():
                self._finish(job, JobState.CANCELLED)
                await self._on_job_done(job)
                return

            job.phase = "playing"
            group_start = time.monotonic()
            job.anchors[("group", AnchorPhase.START)] = group_start
            # group.end 在全部事件结束后回填

            tasks = [
                asyncio.create_task(self._run_event(job, event), name=f"perf-{job.job_id}-{event.id}")
                for event in job.events
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if job.cancel_event.is_set():
                state = JobState.CANCELLED
            elif any(rt.status is EventStatus.FAILED for rt in job.runtimes.values()):
                state = JobState.FAILED
                job.error = "one or more events failed"
            else:
                state = JobState.COMPLETED
            # gather 异常已写入 runtime
            for result in results:
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.exception("表演事件任务异常: {}", result)
            job.anchors[("group", AnchorPhase.END)] = time.monotonic()
            self._finish(job, state)
        except asyncio.CancelledError:
            self._finish(job, JobState.CANCELLED)
            raise
        except Exception as exc:
            logger.exception("Job {} 调度失败", job.job_id)
            job.error = str(exc)
            self._finish(job, JobState.FAILED)
        finally:
            await self._on_job_done(job)

    async def _run_event(self, job: _Job, event: TimelineEvent) -> None:
        runtime = job.runtimes[event.id]
        try:
            fire_at = await self._wait_for_ref(job, event.start)
            if job.cancel_event.is_set():
                runtime.status = EventStatus.CANCELLED
                return
            now = time.monotonic()
            wait_more = fire_at - now
            if wait_more > 0:
                runtime.status = EventStatus.ARMED
                await _wait_or_cancel(wait_more, job.cancel_event)
            if job.cancel_event.is_set():
                runtime.status = EventStatus.CANCELLED
                return

            runtime.status = EventStatus.RUNNING
            await self._execute_event(job, event, runtime)
            if runtime.status is EventStatus.RUNNING:
                runtime.status = EventStatus.COMPLETED
        except asyncio.CancelledError:
            runtime.status = EventStatus.CANCELLED
            self._mark_anchor(job, event.id, AnchorPhase.END, time.monotonic())
            raise
        except Exception as exc:
            runtime.status = EventStatus.FAILED
            runtime.error = str(exc)
            logger.exception("事件 {} 失败: {}", event.id, exc)
            # 失败也释放 end,避免后继永久挂起
            if (event.id, AnchorPhase.START) not in job.anchors:
                self._mark_anchor(job, event.id, AnchorPhase.START, time.monotonic())
            self._mark_anchor(job, event.id, AnchorPhase.END, time.monotonic())

    async def _wait_for_ref(self, job: _Job, ref: StartRef) -> float:
        """等到依赖锚点可解析,返回 fire_at(monotonic)。"""

        key = (ref.anchor, ref.phase)
        while key not in job.anchors:
            if job.cancel_event.is_set():
                raise asyncio.CancelledError
            await asyncio.sleep(0.02)
        return job.anchors[key] + ref.delay

    async def _execute_event(self, job: _Job, event: TimelineEvent, runtime: EventRuntime) -> None:
        if event.type is EventType.WAIT:
            t0 = time.monotonic()
            self._mark_anchor(job, event.id, AnchorPhase.START, t0)
            runtime.t_start = t0
            seconds = float(event.params["seconds"])
            if seconds > 0:
                await _wait_or_cancel(seconds, job.cancel_event)
            t1 = time.monotonic()
            runtime.t_end = t1
            self._mark_anchor(job, event.id, AnchorPhase.END, t1)
            if job.cancel_event.is_set():
                runtime.status = EventStatus.CANCELLED
            return

        if event.type is EventType.SPEAK:
            await self._execute_speak(job, event, runtime)
            return

        if event.type is EventType.PLAY_EMOTION:
            await self._execute_emotion(job, event, runtime)
            return

        if event.type is EventType.SET_NATIVE_EXPRESSION:
            t0 = time.monotonic()
            self._mark_anchor(job, event.id, AnchorPhase.START, t0)
            runtime.t_start = t0
            await self._host.launch_set_native_expression(
                str(event.params["name"]),
                bool(event.params["active"]),
            )
            t1 = time.monotonic()
            runtime.t_end = t1
            self._mark_anchor(job, event.id, AnchorPhase.END, t1)
            return

        if event.type is EventType.CLEAR_NATIVE_EXPRESSIONS:
            t0 = time.monotonic()
            self._mark_anchor(job, event.id, AnchorPhase.START, t0)
            runtime.t_start = t0
            await self._host.launch_clear_native_expressions()
            t1 = time.monotonic()
            runtime.t_end = t1
            self._mark_anchor(job, event.id, AnchorPhase.END, t1)
            return

        raise ValueError(f"未实现的事件类型: {event.type}")

    async def _execute_speak(self, job: _Job, event: TimelineEvent, runtime: EventRuntime) -> None:
        params = event.params
        await self._run_anchored_action(
            job,
            event,
            runtime,
            bind=self._host.bind_speak_anchors,
            launch=lambda: self._host.launch_speak(str(params["text"])),
            release=self._host.stop_speak,
        )

    async def _execute_emotion(self, job: _Job, event: TimelineEvent, runtime: EventRuntime) -> None:
        params = event.params
        kwargs: dict[str, Any] = {
            "intensity": float(params.get("intensity", 1.0)),
            "transition_duration": params.get("transition_duration"),
        }
        # 有通用 end 约束 → 外部 hold(hold_duration=None),到点 force-release
        if event.end is not None:
            kwargs["hold_duration"] = None
        elif "hold_duration" in params:
            kwargs["hold_duration"] = float(params["hold_duration"])

        await self._run_anchored_action(
            job,
            event,
            runtime,
            bind=self._host.bind_emotion_anchors,
            launch=lambda: self._host.launch_play_emotion(str(params["emotion"]), **kwargs),
            release=self._host.cancel_play_emotion,
        )

    async def _run_anchored_action(
        self,
        job: _Job,
        event: TimelineEvent,
        runtime: EventRuntime,
        *,
        bind: Callable[[Callable[[], None], Callable[[], None]], Callable[[], None]],
        launch: Callable[[], Any],
        release: Callable[[], Any],
    ) -> None:
        """通用:订阅 start/end 锚点 → 可选 end 约束 force-release → launch → 等 end。

        适用于任何「异步表演 + 锚点回报」的 type。
        force-release 只结束表演态;收尾由能力后台完成。
        start/end 必须由底层能力通过 bind 回调上报,调度器不伪造。
        """

        started = asyncio.Event()
        ended = asyncio.Event()

        def _on_start() -> None:
            if not started.is_set():
                t = time.monotonic()
                self._mark_anchor(job, event.id, AnchorPhase.START, t)
                runtime.t_start = t
                started.set()

        def _on_end() -> None:
            if not started.is_set():
                _on_start()
            if not ended.is_set():
                t = time.monotonic()
                self._mark_anchor(job, event.id, AnchorPhase.END, t)
                runtime.t_end = t
                ended.set()

        unbind = bind(_on_start, _on_end)
        force_task: asyncio.Task[None] | None = None
        try:
            if job.cancel_event.is_set():
                runtime.status = EventStatus.CANCELLED
                return
            if event.end is not None:
                # 先挂 force 再 launch,避免 end 锚点极早就绪时竞态
                force_task = asyncio.create_task(
                    self._force_release_when(job, event, release),
                    name=f"perf-end-{event.id}",
                )
            result = launch()
            if asyncio.iscoroutine(result):
                await result
            while not ended.is_set():
                if job.cancel_event.is_set():
                    rel = release()
                    if asyncio.iscoroutine(rel):
                        await rel
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(ended.wait(), timeout=1.0)
                    if not ended.is_set():
                        _on_end()
                    runtime.status = EventStatus.CANCELLED
                    return
                try:
                    await asyncio.wait_for(ended.wait(), timeout=0.1)
                except TimeoutError:
                    continue
            if runtime.status is not EventStatus.CANCELLED:
                runtime.status = EventStatus.COMPLETED
        finally:
            if force_task is not None and not force_task.done():
                force_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await force_task
            unbind()

    async def _force_release_when(
        self,
        job: _Job,
        event: TimelineEvent,
        release: Callable[[], Any],
    ) -> None:
        """等到 end 约束到点后调用 release。

        通用生命周期:任何 type 都可挂 end_*;release 只结束表演态,
        收尾/回落由能力自己后台完成。
        """

        try:
            if event.end is None:
                return
            fire_at = await self._wait_for_ref(job, event.end)
            wait_s = fire_at - time.monotonic()
            if wait_s > 0:
                await _wait_or_cancel(wait_s, job.cancel_event)
            if job.cancel_event.is_set():
                return
            result = release()
            if asyncio.iscoroutine(result):
                await result
        except asyncio.CancelledError:
            return

    def _mark_anchor(self, job: _Job, event_id: str, phase: AnchorPhase, t: float) -> None:
        key = (event_id, phase)
        if key not in job.anchors:
            job.anchors[key] = t

    async def _cancel_job(self, job: _Job) -> None:
        job.cancel_event.set()
        with contextlib.suppress(Exception):
            await self._host.stop_speak()
        with contextlib.suppress(Exception):
            await self._host.cancel_play_emotion()
        task = job.task
        if task is not None and not task.done() and task is not asyncio.current_task():
            # 优先靠 cancel_event 协作退出;超时再强 cancel
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

    def _push_finished(self, snap: JobSnapshot) -> None:
        self._finished.append(snap)
        if len(self._finished) > _FINISHED_LIMIT:
            self._finished = self._finished[-_FINISHED_LIMIT:]

    async def _on_job_done(self, job: _Job) -> None:
        async with self._lock:
            if self._running is job:
                self._running = None
            elif self._running is not None:
                # 已被 remove_job 摘掉 running 指针
                pass
            await self._kick_next_unlocked()

    async def _kick_next_unlocked(self) -> None:
        if self._running is not None:
            return
        if not self._pending:
            return
        nxt = self._pending.pop(0)
        self._running = nxt
        nxt.state = JobState.RUNNING
        nxt.task = asyncio.create_task(self._run_job(nxt))

    def _draft_error(self, message: str, _exc: BaseException | None = None) -> DraftSnapshot:
        base = self.get_draft()
        errors = [*base.errors, message]
        return DraftSnapshot(events=base.events, valid=False, errors=errors)


async def _wait_or_cancel(seconds: float, cancel_event: asyncio.Event) -> None:
    if seconds <= 0:
        return
    try:
        await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
        raise asyncio.CancelledError
    except TimeoutError:
        return


def _validate_graph(events: list[TimelineEvent]) -> list[str]:
    errors: list[str] = []
    ids = {event.id for event in events}
    for event in events:
        for label, ref in (("start", event.start), ("end", event.end)):
            if ref is None:
                continue
            if ref.anchor != "group" and ref.anchor not in ids:
                errors.append(f"{event.id}: 未知 {label}_anchor '{ref.anchor}'")
            if ref.delay < 0:
                errors.append(f"{event.id}: {label} delay 须 >= 0")
            if label == "end" and ref.anchor == event.id:
                errors.append(f"{event.id}: end_anchor 不能指向自身")
    cycle = _find_cycle(events)
    if cycle is not None:
        errors.append(f"依赖成环: {' -> '.join(cycle)}")
    return errors


def _find_cycle(events: list[TimelineEvent]) -> list[str] | None:
    """若事件依赖(忽略 group)成环则返回路径。"""

    graph: dict[str, list[str]] = {event.id: [] for event in events}
    for event in events:
        for ref in (event.start, event.end):
            if ref is None:
                continue
            if ref.anchor != "group" and ref.anchor in graph and ref.anchor != event.id:
                graph[event.id].append(ref.anchor)

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        if node in visiting:
            if node in stack:
                i = stack.index(node)
                return [*stack[i:], node]
            return [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for prev in graph.get(node, []):
            found = dfs(prev)
            if found is not None:
                return found
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for event_id in graph:
        found = dfs(event_id)
        if found is not None:
            return found
    return None


def _speak_overlap_risk(events: list[TimelineEvent]) -> str | None:
    """粗检:多个 speak 均不依赖其它 speak 的 end 时,可能并发。"""

    speaks = [event for event in events if event.type is EventType.SPEAK]
    if len(speaks) <= 1:
        return None

    speak_ids = {event.id for event in speaks}

    def depends_on_speak_end(event: TimelineEvent, seen: set[str]) -> bool:
        if event.id in seen:
            return False
        seen.add(event.id)
        anchor = event.start.anchor
        if anchor in speak_ids and event.start.phase is AnchorPhase.END:
            return True
        if anchor == "group":
            return False
        parent = next((item for item in events if item.id == anchor), None)
        if parent is None:
            return False
        return depends_on_speak_end(parent, seen)

    free = [event.id for event in speaks if not depends_on_speak_end(event, set())]
    if len(free) > 1:
        return (
            f"多个 speak 可能重叠({', '.join(free)});"
            "请把后一句的 start_anchor 设为前一句 id 且 start_phase=end"
        )
    return None

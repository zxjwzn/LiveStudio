"""Performance 纯调度内核测试。"""

from __future__ import annotations

import asyncio
from typing import Any

from livestudio.services.performance import (
    AnchorPhase,
    EventStatus,
    EventType,
    JobState,
    PerformanceEvent,
    PerformanceService,
)


async def _wait_terminal(
    service: PerformanceService,
    job_id: str,
    *,
    ticks: int = 100,
):
    snapshot = service.get_job(job_id)
    for _ in range(ticks):
        snapshot = service.get_job(job_id)
        if snapshot is not None and snapshot.state in {
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.CANCELLED,
        }:
            return snapshot
        await asyncio.sleep(0.01)
    return snapshot


def test_add_event_keeps_generic_payload_and_anchor() -> None:
    service = PerformanceService()
    first = service.add_event("task.opened", {"key": "value"}, event_id="first")
    second = service.add_event(
        "task.dependent",
        {"value": "warm"},
        event_id="second",
        start_anchor="first",
        start_phase="end",
        delay=0.1,
    )

    assert first.valid
    assert second.valid
    assert second.events[0].type is EventType.EVENT
    assert second.events[0].payload == {"key": "value"}
    assert second.events[1].start.anchor == "first"
    assert second.events[1].start.phase is AnchorPhase.END


def test_invalid_event_constraints_are_rejected() -> None:
    service = PerformanceService()

    assert not service.add_event("", {}).valid
    assert not service.add_event("self", event_id="self", start_anchor="self").valid
    assert not service.add_event("group-end", start_phase="end").valid
    assert not service.add_wait_event(float("inf")).valid


def test_remove_event_blocks_dependents() -> None:
    service = PerformanceService()
    service.add_event("first", event_id="first")
    service.add_event("second", event_id="second", start_anchor="first", start_phase="end")

    blocked = service.remove_event("first")
    assert not blocked.valid
    service.remove_event("second")
    assert service.remove_event("first").events == []


async def test_generic_event_emits_start_and_end() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)
    service.add_event("scene.changed", {"scene": "close-up"}, event_id="scene")

    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    snapshot = await _wait_terminal(service, queued.job_id)

    assert snapshot is not None
    assert snapshot.state is JobState.COMPLETED
    assert snapshot.events[0].status is EventStatus.COMPLETED
    assert [(event.name, event.phase) for event in seen] == [
        ("scene.changed", AnchorPhase.START),
        ("scene.changed", AnchorPhase.END),
    ]
    assert seen[0].payload == {"scene": "close-up"}


async def test_wait_event_is_owned_by_scheduler() -> None:
    service = PerformanceService()
    service.add_wait_event(0.04, event_id="pause")

    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    snapshot = await _wait_terminal(service, queued.job_id)

    assert snapshot is not None
    runtime = snapshot.events[0]
    assert runtime.type is EventType.WAIT
    assert runtime.t_start is not None and runtime.t_end is not None
    assert runtime.t_end - runtime.t_start >= 0.03


async def test_relative_start_delay_uses_previous_end() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)
    service.add_event("first", event_id="first")
    service.add_event(
        "second",
        event_id="second",
        start_anchor="first",
        start_phase="end",
        delay=0.03,
    )

    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    await _wait_terminal(service, queued.job_id)

    first_end = next(event.timestamp for event in seen if event.event_id == "first" and event.phase is AnchorPhase.END)
    second_start = next(event.timestamp for event in seen if event.event_id == "second" and event.phase is AnchorPhase.START)
    assert second_start - first_end >= 0.02


async def test_explicit_end_keeps_event_running_until_anchor() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)
    service.add_wait_event(0.04, event_id="clock")
    service.add_event(
        "held",
        event_id="held",
        end_anchor="clock",
        end_phase="end",
    )

    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    snapshot = await _wait_terminal(service, queued.job_id)

    assert snapshot is not None and snapshot.state is JobState.COMPLETED
    held = next(event for event in snapshot.events if event.id == "held")
    assert held.t_start is not None and held.t_end is not None
    assert held.t_end - held.t_start >= 0.03
    phases = [(event.event_id, event.phase) for event in seen]
    assert phases.index(("clock", AnchorPhase.END)) < phases.index(("held", AnchorPhase.END))


async def test_jobs_run_serially() -> None:
    service = PerformanceService()
    service.add_wait_event(0.05, event_id="first")
    first = await service.enqueue_draft()
    service.add_wait_event(0.0, event_id="second")
    second = await service.enqueue_draft()

    assert first.state is JobState.RUNNING
    assert second.state is JobState.PENDING
    assert first.job_id is not None and second.job_id is not None
    await _wait_terminal(service, first.job_id)
    second_snapshot = await _wait_terminal(service, second.job_id)
    assert second_snapshot is not None and second_snapshot.state is JobState.COMPLETED


async def test_remove_job_cancels_running_event() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)
    service.add_wait_event(2.0, event_id="long")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    await asyncio.sleep(0.02)

    removed = await service.remove_job(queued.job_id)
    snapshot = service.get_job(queued.job_id)

    assert removed.ok and removed.cancelled_running
    assert snapshot is not None and snapshot.state is JobState.CANCELLED
    assert snapshot.events[0].status is EventStatus.CANCELLED
    assert [(event.event_id, event.phase) for event in seen] == [
        ("long", AnchorPhase.START),
        ("long", AnchorPhase.END),
    ]


async def test_listener_failure_does_not_fail_scheduling() -> None:
    service = PerformanceService()

    def _raise(_event: PerformanceEvent) -> None:
        raise RuntimeError("listener failed")

    service.subscribe(_raise)
    service.add_event("still-runs")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None

    snapshot = await _wait_terminal(service, queued.job_id)
    assert snapshot is not None and snapshot.state is JobState.COMPLETED


async def test_unsubscribe_stops_notifications() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    unsubscribe = service.subscribe(seen.append)
    unsubscribe()
    service.add_event("silent")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None

    await _wait_terminal(service, queued.job_id)
    assert seen == []


async def test_clear_draft_and_empty_enqueue() -> None:
    service = PerformanceService()
    service.add_event("temporary")
    assert service.get_draft().events
    service.clear_draft()

    result = await service.enqueue_draft()
    assert not result.ok
    assert result.error == "empty_draft"


async def test_finished_limit_zero_returns_empty_list() -> None:
    service = PerformanceService()
    service.add_event("instant")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    await _wait_terminal(service, queued.job_id)

    assert service.list_jobs(include_finished=True, limit=0).finished == []


async def test_registered_handler_drives_end_on_completion() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)

    async def hold(_payload: dict[str, Any]) -> None:
        await asyncio.sleep(0.03)

    service.register_handler("action.hold", hold)
    service.add_event("action.hold", {"v": 1}, event_id="hold")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    snapshot = await _wait_terminal(service, queued.job_id)

    assert snapshot is not None
    assert snapshot.state is JobState.COMPLETED
    runtime = snapshot.events[0]
    assert runtime.status is EventStatus.COMPLETED
    assert runtime.t_start is not None and runtime.t_end is not None
    assert runtime.t_end - runtime.t_start >= 0.02
    assert [(event.name, event.phase) for event in seen] == [
        ("action.hold", AnchorPhase.START),
        ("action.hold", AnchorPhase.END),
    ]


async def test_handler_exception_marks_failed_and_stamps_end() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)

    async def boom(_payload: dict[str, Any]) -> None:
        await asyncio.sleep(0.01)
        raise RuntimeError("handler exploded")

    service.register_handler("action.boom", boom)
    service.add_event("action.boom", event_id="boom")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    snapshot = await _wait_terminal(service, queued.job_id)

    assert snapshot is not None
    assert snapshot.state is JobState.FAILED
    runtime = snapshot.events[0]
    assert runtime.status is EventStatus.FAILED
    assert runtime.error is not None
    # END 仍盖章:依赖方不会因生产者失败而永久等待
    assert runtime.t_start is not None and runtime.t_end is not None
    assert [(event.event_id, event.phase) for event in seen] == [
        ("boom", AnchorPhase.START),
        ("boom", AnchorPhase.END),
    ]


async def test_handler_cancellation_when_job_removed() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)

    async def long_hold(_payload: dict[str, Any]) -> None:
        await asyncio.sleep(2.0)

    service.register_handler("action.long", long_hold)
    service.add_event("action.long", event_id="long")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    await asyncio.sleep(0.02)

    removed = await service.remove_job(queued.job_id)
    snapshot = service.get_job(queued.job_id)

    assert removed.ok and removed.cancelled_running
    assert snapshot is not None and snapshot.state is JobState.CANCELLED
    runtime = snapshot.events[0]
    assert runtime.status is EventStatus.CANCELLED
    assert runtime.t_start is not None and runtime.t_end is not None
    # 远小于 2.0s:handler 被及时取消,而非自然结束
    assert runtime.t_end - runtime.t_start < 0.5
    assert [(event.event_id, event.phase) for event in seen] == [
        ("long", AnchorPhase.START),
        ("long", AnchorPhase.END),
    ]


async def test_dependent_starts_after_handler_completion() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)

    async def hold(_payload: dict[str, Any]) -> None:
        await asyncio.sleep(0.04)  # 未知时长,调度器事先不知

    service.register_handler("action.hold", hold)
    service.add_event("action.hold", event_id="a")
    service.add_event("follower", event_id="b", start_anchor="a", start_phase="end", delay=0.0)
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    await _wait_terminal(service, queued.job_id)

    a_end = next(
        event.timestamp for event in seen if event.event_id == "a" and event.phase is AnchorPhase.END
    )
    b_start = next(
        event.timestamp for event in seen if event.event_id == "b" and event.phase is AnchorPhase.START
    )
    # b 在 a 真正完成(handler 返回)之后才起播,验证未知时长级联
    assert b_start >= a_end


async def test_unregister_handler_falls_back_to_instantaneous() -> None:
    service = PerformanceService()

    async def hold(_payload: dict[str, Any]) -> None:
        await asyncio.sleep(0.05)

    unregister = service.register_handler("action.hold", hold)
    unregister()
    service.add_event("action.hold", event_id="hold")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    snapshot = await _wait_terminal(service, queued.job_id)

    assert snapshot is not None and snapshot.state is JobState.COMPLETED
    runtime = snapshot.events[0]
    # 无 handler -> 回退瞬时 END,t_start 与 t_end 几乎相等
    assert runtime.t_start is not None and runtime.t_end is not None
    assert runtime.t_end - runtime.t_start < 0.03


async def test_handler_takes_precedence_over_end_anchor() -> None:
    service = PerformanceService()
    seen: list[PerformanceEvent] = []
    service.subscribe(seen.append)

    service.add_wait_event(0.5, event_id="clock")  # end_anchor 目标:0.5s

    async def quick(_payload: dict[str, Any]) -> None:
        await asyncio.sleep(0.03)

    service.register_handler("action.quick", quick)
    service.add_event("action.quick", event_id="held", end_anchor="clock", end_phase="end")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    snapshot = await _wait_terminal(service, queued.job_id)

    assert snapshot is not None and snapshot.state is JobState.COMPLETED
    held = next(event for event in snapshot.events if event.id == "held")
    assert held.status is EventStatus.COMPLETED
    assert held.t_start is not None and held.t_end is not None
    # handler ~0.03s 完成,远早于 clock 的 0.5s:证明 end_anchor 被忽略
    assert held.t_end - held.t_start < 0.2


async def test_handler_receives_payload_copy() -> None:
    service = PerformanceService()
    received: list[dict[str, Any]] = []

    async def capture(payload: dict[str, Any]) -> None:
        payload["mutated"] = True
        received.append(payload)
        await asyncio.sleep(0.0)

    service.register_handler("action.capture", capture)
    service.add_event("action.capture", {"original": 1}, event_id="cap")
    queued = await service.enqueue_draft()
    assert queued.job_id is not None
    snapshot = await _wait_terminal(service, queued.job_id)

    assert snapshot is not None
    assert received and received[0].get("original") == 1
    runtime = next(event for event in snapshot.events if event.id == "cap")
    # handler 拿到的是副本,原始事件 payload 未被污染
    assert "mutated" not in runtime.payload
    assert runtime.payload == {"original": 1}


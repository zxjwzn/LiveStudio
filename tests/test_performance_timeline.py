"""表演时间线:草稿 / 队列 / 锚点调度"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from livestudio.services.performance import EventStatus, JobState, PerformanceService


class RecordingHost:
    """可脚本化的 host:speak/emotion 用事件模拟锚点。"""

    def __init__(self) -> None:
        self.speaks: list[str] = []
        self.emotions: list[str] = []
        self.natives: list[tuple[str, bool]] = []
        self._speak_start: Callable[[], None] | None = None
        self._speak_end: Callable[[], None] | None = None
        self._emotion_start: Callable[[], None] | None = None
        self._emotion_end: Callable[[], None] | None = None
        self._speak_auto = True
        self._emotion_auto = True

    async def launch_speak(self, text: str) -> None:
        self.speaks.append(text)
        if self._speak_auto:
            if self._speak_start:
                self._speak_start()
            await asyncio.sleep(0.05)
            if self._speak_end:
                self._speak_end()

    async def stop_speak(self) -> None:
        if self._speak_end:
            self._speak_end()

    async def launch_play_emotion(
        self,
        emotion: str,
        *,
        intensity: float = 1.0,
        transition_duration: float | None = None,
        hold_duration: float | None | object = ...,
    ) -> None:
        """与真实 ExpressionController 一致: launch 快返回;无限保持靠 cancel 结束。

        end 语义 = 开始回中性(不阻塞在恢复上)。cancel 只发信号,end 在短任务里触发。
        """

        _ = (intensity, transition_duration)
        self.emotions.append(emotion)
        if not self._emotion_auto:
            return
        if self._emotion_start:
            self._emotion_start()
        if hold_duration is None:
            # 无限保持:不阻塞 launch;cancel 后 fire end,恢复可后台继续
            self._emotion_hold_open = True
            self._emotion_restore_done = asyncio.Event()
            return
        await asyncio.sleep(0.03)
        if self._emotion_end:
            self._emotion_end()
        # 模拟 end 后后台恢复
        self._emotion_restore_done = asyncio.Event()
        self._emotion_restore_done.set()

    async def cancel_play_emotion(self) -> None:
        """只释放 hold;end 立即 fire;恢复可在后台。"""

        if getattr(self, "_emotion_hold_open", False):
            self._emotion_hold_open = False
            if self._emotion_end:
                self._emotion_end()
            # 后台模拟恢复耗时,不阻塞 cancel 返回
            async def _restore() -> None:
                await asyncio.sleep(0.05)
                if getattr(self, "_emotion_restore_done", None) is not None:
                    self._emotion_restore_done.set()

            asyncio.create_task(_restore())
            return
        if self._emotion_end:
            self._emotion_end()

    async def launch_set_native_expression(self, name: str, active: bool) -> None:
        self.natives.append((name, active))

    async def launch_clear_native_expressions(self) -> None:
        self.natives.append(("*", False))

    def bind_speak_anchors(self, on_start, on_end):
        self._speak_start = on_start
        self._speak_end = on_end

        def _unbind() -> None:
            self._speak_start = None
            self._speak_end = None

        return _unbind

    def bind_emotion_anchors(self, on_start, on_end):
        self._emotion_start = on_start
        self._emotion_end = on_end

        def _unbind() -> None:
            self._emotion_start = None
            self._emotion_end = None

        return _unbind


def test_add_event_validates_and_binds() -> None:
    host = RecordingHost()
    svc = PerformanceService(host)
    d1 = svc.add_event("speak", {"text": "hi"}, id="s")
    assert d1.valid
    d2 = svc.add_event(
        "play_emotion",
        {"emotion": "joy"},
        id="e",
        start_anchor="s",
        start_phase="start",
        delay=0.1,
    )
    assert d2.valid
    assert len(d2.events) == 2
    bad = svc.add_event("speak", {"text": ""})
    assert not bad.valid


def test_remove_event_blocks_dependents() -> None:
    svc = PerformanceService(RecordingHost())
    svc.add_event("speak", {"text": "a"}, id="s")
    svc.add_event("wait", {"seconds": 0.01}, id="w", start_anchor="s", start_phase="end")
    blocked = svc.remove_event("s")
    assert not blocked.valid
    svc.remove_event("w")
    ok = svc.remove_event("s")
    assert ok.valid
    assert ok.events == []


async def test_enqueue_runs_wait_and_completes() -> None:
    svc = PerformanceService(RecordingHost())
    svc.add_event("wait", {"seconds": 0.05}, id="w")
    result = await svc.enqueue_draft(delay=0)
    assert result.ok
    job_id = result.job_id
    assert job_id
    for _ in range(100):
        snap = svc.get_job(job_id)
        assert snap is not None
        if snap.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            break
        await asyncio.sleep(0.02)
    snap = svc.get_job(job_id)
    assert snap is not None
    assert snap.state is JobState.COMPLETED
    assert snap.events[0].status is EventStatus.COMPLETED


async def test_speak_then_emotion_relative_start() -> None:
    host = RecordingHost()
    svc = PerformanceService(host)
    svc.add_event("speak", {"text": "hello"}, id="s")
    svc.add_event(
        "play_emotion",
        {"emotion": "joy"},
        id="e",
        start_anchor="s",
        start_phase="start",
        delay=0.02,
    )
    result = await svc.enqueue_draft()
    assert result.ok
    job_id = result.job_id
    for _ in range(100):
        snap = svc.get_job(job_id)  # type: ignore[arg-type]
        if snap and snap.state is JobState.COMPLETED:
            break
        await asyncio.sleep(0.02)
    assert host.speaks == ["hello"]
    assert host.emotions == ["joy"]
    snap = svc.get_job(job_id)  # type: ignore[arg-type]
    assert snap is not None
    assert snap.state is JobState.COMPLETED


async def test_queue_serial_second_job_waits() -> None:
    host = RecordingHost()
    svc = PerformanceService(host)
    svc.add_event("wait", {"seconds": 0.12}, id="w1")
    r1 = await svc.enqueue_draft()
    svc.add_event("wait", {"seconds": 0.01}, id="w2")
    r2 = await svc.enqueue_draft()
    assert r1.state is JobState.RUNNING
    assert r2.state is JobState.PENDING
    # 完成两者
    for _ in range(100):
        q = svc.list_jobs(include_finished=True)
        finished_ids = {j.job_id for j in q.finished}
        if r1.job_id in finished_ids and r2.job_id in finished_ids:
            break
        await asyncio.sleep(0.03)
    q = svc.list_jobs(include_finished=True)
    states = {j.job_id: j.state for j in q.finished}
    assert states[r1.job_id] is JobState.COMPLETED  # type: ignore[index]
    assert states[r2.job_id] is JobState.COMPLETED  # type: ignore[index]


async def test_remove_job_cancels_running() -> None:
    host = RecordingHost()
    svc = PerformanceService(host)
    svc.add_event("wait", {"seconds": 2.0}, id="w")
    r = await svc.enqueue_draft()
    assert r.job_id
    await asyncio.sleep(0.02)
    removed = await svc.remove_job(r.job_id)
    assert removed.ok
    assert removed.cancelled_running
    snap = svc.get_job(r.job_id)
    assert snap is not None
    assert snap.state is JobState.CANCELLED


async def test_speak_overlap_rejected() -> None:
    svc = PerformanceService(RecordingHost())
    svc.add_event("speak", {"text": "a"}, id="s1")
    svc.add_event("speak", {"text": "b"}, id="s2")
    r = await svc.enqueue_draft()
    assert not r.ok
    assert r.error == "speak_overlap"


async def test_enqueue_delay_and_speak_end_chain() -> None:
    """enqueue_delay 后再开演;第二句 speak 绑第一句 end。"""

    host = RecordingHost()
    svc = PerformanceService(host)
    svc.add_event("speak", {"text": "one"}, id="s1")
    svc.add_event(
        "speak",
        {"text": "two"},
        id="s2",
        start_anchor="s1",
        start_phase="end",
        delay=0.01,
    )
    r = await svc.enqueue_draft(delay=0.05)
    assert r.ok
    for _ in range(150):
        snap = svc.get_job(r.job_id)  # type: ignore[arg-type]
        if snap and snap.state is JobState.COMPLETED:
            break
        await asyncio.sleep(0.02)
    assert host.speaks == ["one", "two"]
    snap = svc.get_job(r.job_id)  # type: ignore[arg-type]
    assert snap is not None
    assert snap.state is JobState.COMPLETED


async def test_native_and_clear() -> None:
    host = RecordingHost()
    svc = PerformanceService(host)
    svc.add_event("set_native_expression", {"name": "a", "active": True})
    svc.add_event("clear_native_expressions", {})
    r = await svc.enqueue_draft()
    for _ in range(50):
        snap = svc.get_job(r.job_id)  # type: ignore[arg-type]
        if snap and snap.state is JobState.COMPLETED:
            break
        await asyncio.sleep(0.02)
    assert host.natives == [("a", True), ("*", False)]


async def test_clear_draft() -> None:
    svc = PerformanceService(RecordingHost())
    svc.add_event("wait", {"seconds": 0.01})
    assert len(svc.get_draft().events) == 1
    svc.clear_draft()
    assert svc.get_draft().events == []

async def test_end_constraint_emotion_until_speak_end() -> None:
    """通用 end 约束:表情 start=speak.start, end=speak.end,撑满语音。"""

    host = RecordingHost()
    svc = PerformanceService(host)
    svc.add_event("speak", {"text": "hello"}, id="s")
    d = svc.add_event(
        "play_emotion",
        {"emotion": "joy"},
        id="e",
        start_anchor="s",
        start_phase="start",
        delay=0,
        end_anchor="s",
        end_phase="end",
        end_delay=0,
    )
    assert d.valid
    assert d.events[-1].end is not None
    r = await svc.enqueue_draft()
    assert r.ok
    for _ in range(150):
        snap = svc.get_job(r.job_id)  # type: ignore[arg-type]
        if snap and snap.state is JobState.COMPLETED:
            break
        await asyncio.sleep(0.02)
    assert host.speaks == ["hello"]
    assert host.emotions == ["joy"]
    snap = svc.get_job(r.job_id)  # type: ignore[arg-type]
    assert snap is not None
    assert snap.state is JobState.COMPLETED
    # 两个事件都应 completed
    by_id = {e.id: e for e in snap.events}
    assert by_id["s"].status is EventStatus.COMPLETED
    assert by_id["e"].status is EventStatus.COMPLETED


async def test_end_constraint_rejects_self_anchor() -> None:
    svc = PerformanceService(RecordingHost())
    svc.add_event("speak", {"text": "a"}, id="s")
    bad = svc.add_event(
        "play_emotion",
        {"emotion": "joy"},
        id="e",
        end_anchor="e",
        end_phase="end",
    )
    assert not bad.valid


async def test_force_release_completes_event_before_restore() -> None:
    """通用 end:force-release 后事件 completed,不因后台恢复拖住 Job。"""

    host = RecordingHost()
    host._emotion_auto = True
    svc = PerformanceService(host)
    svc.add_event("speak", {"text": "hello"}, id="s")
    svc.add_event(
        "play_emotion",
        {"emotion": "joy"},
        id="e",
        start_anchor="s",
        start_phase="start",
        end_anchor="s",
        end_phase="end",
    )
    r = await svc.enqueue_draft()
    assert r.ok
    for _ in range(150):
        snap = svc.get_job(r.job_id)  # type: ignore[arg-type]
        if snap and snap.state is JobState.COMPLETED:
            break
        await asyncio.sleep(0.02)
    snap = svc.get_job(r.job_id)  # type: ignore[arg-type]
    assert snap is not None
    assert snap.state is JobState.COMPLETED
    by_id = {e.id: e for e in snap.events}
    assert by_id["e"].status is EventStatus.COMPLETED
    # Job 完成后恢复才可能仍在进行;这里允许 restore 稍后完成
    if getattr(host, "_emotion_restore_done", None) is not None:
        await asyncio.wait_for(host._emotion_restore_done.wait(), timeout=1.0)

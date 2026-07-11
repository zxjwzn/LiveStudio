"""MCP 工具集反射与分发测试

验证「通用动词上移基类、标 @tool(builtin=True) 固有化;平台特有工具留在子类」的反射机制,
以及表演时间线工具(add_event/enqueue_draft/…)经 toolset.call 的端到端行为。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from livestudio.mcp.constants import TOOL_MARK
from livestudio.mcp.platforms.vtubestudio_toolset import VTubeStudioToolset
from livestudio.mcp.toolset import PlatformToolset

from .mcp_fakes import UNIVERSAL_VERBS, _FakeApp, _FakeToolset


def _as_dict(value: object) -> dict[str, Any]:
    """toolset.call 返回 object;测试里断言前收窄为 dict。"""

    assert isinstance(value, dict)
    return value




def _tool_meta_map(cls: type) -> dict[str, Any]:
    """类自身直接定义的 @tool 方法 -> 其 _ToolMeta(builtin 标记)。"""

    result: dict[str, Any] = {}
    for name, fn in vars(cls).items():
        meta = getattr(fn, TOOL_MARK, None)
        if meta is not None:
            result[name] = meta
    return result


async def _wait_job_terminal(toolset: _FakeToolset, job_id: str, *, ticks: int = 100) -> dict[str, Any]:
    """轮询 get_job 直到 Job 进入终态;返回 get_job 的完整结果 dict。"""

    last: dict[str, Any] = {}
    for _ in range(ticks):
        result = _as_dict(await toolset.call("get_job", {"job_id": job_id}))
        last = result
        job = result.get("job")
        if result.get("ok") and isinstance(job, dict):
            if job.get("state") in {"completed", "failed", "cancelled"}:
                return result
        await asyncio.sleep(0.02)
    return last


def test_base_defines_builtin_verbs() -> None:
    """基类 PlatformToolset 直接定义全部 @tool(builtin=True) 通用动词(含时间线)。"""

    metas = _tool_meta_map(PlatformToolset)
    assert set(metas) == UNIVERSAL_VERBS
    assert all(meta.builtin for meta in metas.values())


def test_vtubestudio_keeps_only_native_expressions() -> None:
    """VTubeStudioToolset 只直接定义 3 个 native expressions @tool(非 builtin),不重声明通用动词。"""

    metas = _tool_meta_map(VTubeStudioToolset)
    assert set(metas) == {"list_native_expressions", "set_native_expression", "clear_native_expressions"}
    assert all(not meta.builtin for meta in metas.values())
    assert not (UNIVERSAL_VERBS & set(metas))


def test_reflection_splits_universal_and_specific() -> None:
    """实例反射:universal_tools() = 通用动词;tools() = 平台特有(ping)。"""

    toolset = _FakeToolset(_FakeApp())
    universal_names = {t.name for t in toolset.universal_tools()}
    specific_names = {t.name for t in toolset.tools()}
    assert universal_names == UNIVERSAL_VERBS
    assert specific_names == {"ping"}
    assert not (universal_names & specific_names)


def test_timeline_tool_descriptions_document_contract() -> None:
    """时间线工具 description 含关键契约词,供 LLM 读 docstring 学会编排。"""

    toolset = _FakeToolset(_FakeApp())
    by_name = {t.name: t for t in toolset.universal_tools()}
    add_desc = by_name["add_event"].description or ""
    enq_desc = by_name["enqueue_draft"].description or ""
    rm_desc = by_name["remove_job"].description or ""
    assert "speak" in add_desc and "play_emotion" in add_desc
    assert "start_anchor" in add_desc or "锚点" in add_desc
    assert "enqueue_draft" in add_desc
    assert "pending" in enq_desc or "排队" in enq_desc
    assert "delay" in enq_desc
    assert "打断" in rm_desc or "取消" in rm_desc


async def test_call_dispatches_universal_verb() -> None:
    """call('connect') 走基类通用动词,调到 app.connect 并返回其拼装结果。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    result = await toolset.call("connect", {})
    assert app.connect_calls == 1
    assert result == "已连接平台，当前模型：TestModel。"


async def test_call_dispatches_specific_tool() -> None:
    """call('ping') 走子类特有工具。"""

    toolset = _FakeToolset(_FakeApp())
    assert await toolset.call("ping", {}) == "pong"


async def test_call_unknown_raises_key_error() -> None:
    """未知工具名抛 KeyError(server 据此收敛为对 LLM 的错误)。"""

    toolset = _FakeToolset(_FakeApp())
    with pytest.raises(KeyError):
        await toolset.call("nope", {})


async def test_add_event_and_get_draft() -> None:
    """add_event 写入草稿;get_draft 可见;非法 type 记入 errors。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    result = _as_dict(
        await toolset.call(
            "add_event",
            {"event_type": "wait", "params": {"seconds": 0.01}, "event_id": "w1"},
        )
    )
    assert result["valid"] is True
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "w1"
    draft = _as_dict(await toolset.call("get_draft", {}))
    assert len(draft["events"]) == 1
    bad = _as_dict(await toolset.call("add_event", {"event_type": "nope", "params": {}}))
    assert bad["valid"] is False


async def test_remove_event_and_clear_draft() -> None:
    """remove_event 删草稿事件;有依赖时拒绝;clear_draft 清空。"""

    toolset = _FakeToolset(_FakeApp())
    await toolset.call("add_event", {"event_type": "speak", "params": {"text": "a"}, "event_id": "s"})
    await toolset.call(
        "add_event",
        {"event_type": "wait", "params": {"seconds": 0.01}, "event_id": "w", "start_anchor": "s", "start_phase": "end"},
    )
    blocked = _as_dict(await toolset.call("remove_event", {"event_id": "s"}))
    assert blocked["valid"] is False
    await toolset.call("remove_event", {"event_id": "w"})
    ok = _as_dict(await toolset.call("remove_event", {"event_id": "s"}))
    assert ok["valid"] is True
    assert ok["events"] == []
    await toolset.call("add_event", {"event_type": "wait", "params": {"seconds": 0.01}})
    cleared = _as_dict(await toolset.call("clear_draft", {}))
    assert cleared["events"] == []


async def test_enqueue_wait_completes() -> None:
    """enqueue_draft 入队 wait 并跑到 completed。"""

    toolset = _FakeToolset(_FakeApp())
    await toolset.call("add_event", {"event_type": "wait", "params": {"seconds": 0.05}, "event_id": "w"})
    enq = _as_dict(await toolset.call("enqueue_draft", {"delay": 0}))
    assert enq["ok"] is True
    assert enq["job_id"]
    # 草稿应已清空
    draft = _as_dict(await toolset.call("get_draft", {}))
    assert draft["events"] == []
    terminal = await _wait_job_terminal(toolset, enq["job_id"])
    assert terminal["ok"] is True
    assert terminal["job"]["state"] == "completed"


async def test_enqueue_speak_and_emotion_parallel() -> None:
    """speak + play_emotion 同绑 group.start 并行;host 收到两者。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    await toolset.call("add_event", {"event_type": "speak", "params": {"text": "hello"}, "event_id": "s"})
    await toolset.call("add_event", {"event_type": "play_emotion", "params": {"emotion": "joy"}, "event_id": "e"})
    enq = _as_dict(await toolset.call("enqueue_draft", {}))
    assert enq["ok"] is True
    terminal = await _wait_job_terminal(toolset, enq["job_id"])
    assert terminal["job"]["state"] == "completed"
    assert app.perf_host.speaks == ["hello"]
    assert app.perf_host.emotions == ["joy"]


async def test_enqueue_emotion_after_speak_start() -> None:
    """play_emotion 绑 speak.start+delay 在开口后触发。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    await toolset.call("add_event", {"event_type": "speak", "params": {"text": "hi"}, "event_id": "s"})
    await toolset.call(
        "add_event",
        {
            "event_type": "play_emotion",
            "params": {"emotion": "joy"},
            "event_id": "e",
            "start_anchor": "s",
            "start_phase": "start",
            "delay": 0.02,
        },
    )
    enq = _as_dict(await toolset.call("enqueue_draft", {}))
    assert enq["ok"] is True
    terminal = await _wait_job_terminal(toolset, enq["job_id"])
    assert terminal["job"]["state"] == "completed"
    assert app.perf_host.speaks == ["hi"]
    assert app.perf_host.emotions == ["joy"]


async def test_enqueue_rejects_speak_overlap() -> None:
    """两个 speak 都挂 group.start 时 enqueue 拒绝,草稿保留。"""

    toolset = _FakeToolset(_FakeApp())
    await toolset.call("add_event", {"event_type": "speak", "params": {"text": "a"}, "event_id": "s1"})
    await toolset.call("add_event", {"event_type": "speak", "params": {"text": "b"}, "event_id": "s2"})
    enq = _as_dict(await toolset.call("enqueue_draft", {}))
    assert enq["ok"] is False
    assert enq["error"] == "speak_overlap"
    draft = _as_dict(await toolset.call("get_draft", {}))
    assert len(draft["events"]) == 2


async def test_enqueue_empty_draft_fails() -> None:
    toolset = _FakeToolset(_FakeApp())
    enq = _as_dict(await toolset.call("enqueue_draft", {}))
    assert enq["ok"] is False
    assert enq["error"] == "empty_draft"


async def test_queue_serial_and_list_jobs() -> None:
    """第二单 pending;list_jobs 可见;顺序完成后 finished 含两单。"""

    toolset = _FakeToolset(_FakeApp())
    await toolset.call("add_event", {"event_type": "wait", "params": {"seconds": 0.1}, "event_id": "w1"})
    r1 = _as_dict(await toolset.call("enqueue_draft", {}))
    await toolset.call("add_event", {"event_type": "wait", "params": {"seconds": 0.01}, "event_id": "w2"})
    r2 = _as_dict(await toolset.call("enqueue_draft", {}))
    assert r1["state"] == "running"
    assert r2["state"] == "pending"
    jobs = _as_dict(await toolset.call("list_jobs", {}))
    assert jobs["running"] is not None
    assert len(jobs["pending"]) == 1
    await _wait_job_terminal(toolset, r1["job_id"])
    await _wait_job_terminal(toolset, r2["job_id"])
    done = _as_dict(await toolset.call("list_jobs", {"include_finished": True}))
    finished_ids = {j["job_id"] for j in done["finished"]}
    assert r1["job_id"] in finished_ids
    assert r2["job_id"] in finished_ids


async def test_remove_job_cancels_running() -> None:
    """remove_job 取消 running wait。"""

    toolset = _FakeToolset(_FakeApp())
    await toolset.call("add_event", {"event_type": "wait", "params": {"seconds": 2.0}, "event_id": "w"})
    enq = _as_dict(await toolset.call("enqueue_draft", {}))
    await asyncio.sleep(0.02)
    removed = _as_dict(await toolset.call("remove_job", {"job_id": enq["job_id"]}))
    assert removed["ok"] is True
    assert removed["cancelled_running"] is True
    job = _as_dict(await toolset.call("get_job", {"job_id": enq["job_id"]}))
    assert job["ok"] is True
    assert job["job"]["state"] == "cancelled"


async def test_remove_job_all_clears_queue() -> None:
    """remove_job(clear_all=true) 清 running+pending。"""

    toolset = _FakeToolset(_FakeApp())
    await toolset.call("add_event", {"event_type": "wait", "params": {"seconds": 1.0}})
    await toolset.call("enqueue_draft", {})
    await toolset.call("add_event", {"event_type": "wait", "params": {"seconds": 1.0}})
    await toolset.call("enqueue_draft", {})
    removed = _as_dict(await toolset.call("remove_job", {"clear_all": True}))
    assert removed["ok"] is True
    jobs = _as_dict(await toolset.call("list_jobs", {}))
    assert jobs["running"] is None
    assert jobs["pending"] == []


async def test_native_expression_events() -> None:
    """set/clear_native_expression 瞬时事件经队列执行。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    await toolset.call(
        "add_event",
        {"event_type": "set_native_expression", "params": {"name": "smile", "active": True}},
    )
    await toolset.call("add_event", {"event_type": "clear_native_expressions", "params": {}})
    enq = _as_dict(await toolset.call("enqueue_draft", {}))
    assert enq["ok"] is True
    terminal = await _wait_job_terminal(toolset, enq["job_id"])
    assert terminal["job"]["state"] == "completed"
    assert ("smile", True) in app.perf_host.natives
    assert ("*", False) in app.perf_host.natives


async def test_enqueue_delay_delays_start() -> None:
    """enqueue_draft(delay) 在 running 后先 starting_delay 再执行。"""

    toolset = _FakeToolset(_FakeApp())
    await toolset.call("add_event", {"event_type": "wait", "params": {"seconds": 0.01}, "event_id": "w"})
    enq = _as_dict(await toolset.call("enqueue_draft", {"delay": 0.08}))
    assert enq["ok"] is True
    # 刚入队应仍在 starting_delay 或很快 playing
    mid = _as_dict(await toolset.call("get_job", {"job_id": enq["job_id"]}))
    assert mid["ok"] is True
    assert mid["job"]["state"] == "running"
    terminal = await _wait_job_terminal(toolset, enq["job_id"])
    assert terminal["job"]["state"] == "completed"


async def test_get_job_not_found() -> None:
    toolset = _FakeToolset(_FakeApp())
    result = _as_dict(await toolset.call("get_job", {"job_id": "job_missing"}))
    assert result["ok"] is False
    assert result["error"] == "not_found"


async def test_emotion_end_until_speak() -> None:
    """MCP: play_emotion end_anchor=speak.end 撑到语音结束。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    await toolset.call("add_event", {"event_type": "speak", "params": {"text": "hi"}, "event_id": "s"})
    await toolset.call(
        "add_event",
        {
            "event_type": "play_emotion",
            "params": {"emotion": "joy"},
            "event_id": "e",
            "start_anchor": "s",
            "start_phase": "start",
            "delay": 0,
            "end_anchor": "s",
            "end_phase": "end",
            "end_delay": 0,
        },
    )
    enq = _as_dict(await toolset.call("enqueue_draft", {}))
    assert enq["ok"] is True
    terminal = await _wait_job_terminal(toolset, enq["job_id"])
    assert terminal["job"]["state"] == "completed"
    assert app.perf_host.speaks == ["hi"]
    assert app.perf_host.emotions == ["joy"]


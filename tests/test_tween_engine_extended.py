"""扩展 ParameterTweenEngine 测试

覆盖：
- release / release_many / release_all
- cancel / cancel_all
- restart
- keep-alive 循环
- 实际插值正确性（线性缓动）
- delay 延迟
- add 模式
- 高优先级抢占正在运行的低优先级缓动
- 不同参数并发缓动
- _resolve_easing 未知函数名报错
- start 重复调用
- start_value=None 从 controlled_params 继承
- duration=0 且 start==end 走即时路径
"""

from __future__ import annotations

import asyncio

import pytest

from livestudio.services.tween import Easing, ParameterTweenEngine, TweenRequest
from tests.conftest import _SenderRecorder

# ── release ──────────────────────────────────────────────────────────


async def test_release_removes_controlled_param() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    await engine.tween(
        TweenRequest(
            parameter_name="A",
            end_value=1.0,
            duration=0.0,
            easing=Easing.linear,
        ),
    )
    assert "A" in engine.controlled_params

    await engine.release("A")

    assert "A" not in engine.controlled_params
    assert "A" not in engine.active_parameters


async def test_release_cancels_running_tween() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    task = asyncio.create_task(
        engine.tween(
            TweenRequest(
                parameter_name="B",
                end_value=1.0,
                duration=5.0,
                easing=Easing.linear,
            ),
        ),
    )
    await asyncio.sleep(0.05)

    await engine.release("B")
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "B" not in engine.controlled_params
    assert task.done()


async def test_release_nonexistent_parameter_is_noop() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    await engine.release("nonexistent")  # 不应抛异常


# ── release_many ─────────────────────────────────────────────────────


async def test_release_many_releases_multiple_params() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    for name in ("X", "Y", "Z"):
        await engine.tween(
            TweenRequest(
                parameter_name=name,
                end_value=0.5,
                duration=0.0,
                easing=Easing.linear,
            ),
        )
    assert {"X", "Y", "Z"} == set(engine.controlled_params.keys())

    await engine.release_many(["X", "Z"])

    assert set(engine.controlled_params.keys()) == {"Y"}


# ── release_all ──────────────────────────────────────────────────────


async def test_release_all_clears_everything() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    for name in ("A", "B"):
        await engine.tween(
            TweenRequest(
                parameter_name=name,
                end_value=1.0,
                duration=0.0,
                easing=Easing.linear,
            ),
        )
    assert len(engine.controlled_params) == 2

    await engine.release_all()

    assert engine.controlled_params == {}


# ── cancel ───────────────────────────────────────────────────────────


async def test_cancel_stops_tween_but_keeps_controlled_param() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    task = asyncio.create_task(
        engine.tween(
            TweenRequest(
                parameter_name="C",
                end_value=1.0,
                duration=5.0,
                easing=Easing.linear,
            ),
        ),
    )
    await asyncio.sleep(0.05)

    await engine.cancel("C")
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "C" not in engine.active_parameters
    # cancel 不释放控制权，参数值应保留
    assert "C" in engine.controlled_params
    assert task.done()


async def test_cancel_with_release_flag_also_removes_param() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    task = asyncio.create_task(
        engine.tween(
            TweenRequest(
                parameter_name="D",
                end_value=1.0,
                duration=5.0,
                easing=Easing.linear,
            ),
        ),
    )
    await asyncio.sleep(0.05)

    await engine.cancel("D", release=True)
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "D" not in engine.controlled_params
    assert task.done()


# ── cancel_all ───────────────────────────────────────────────────────


async def test_cancel_all_stops_all_tweens_but_keeps_params() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    tasks = []
    for name in ("E", "F"):
        t = asyncio.create_task(
            engine.tween(
                TweenRequest(
                    parameter_name=name,
                    end_value=1.0,
                    duration=5.0,
                    easing=Easing.linear,
                ),
            ),
        )
        tasks.append(t)
    await asyncio.sleep(0.05)

    await engine.cancel_all()

    for t in tasks:
        with pytest.raises(asyncio.CancelledError):
            await t

    assert engine.active_parameters == ()
    # 控制权保留
    assert "E" in engine.controlled_params
    assert "F" in engine.controlled_params
    for t in tasks:
        assert t.done()


# ── restart ──────────────────────────────────────────────────────────


async def test_restart_clears_state_and_restarts_keep_alive() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)
    engine.start()
    assert engine.is_running

    await engine.tween(
        TweenRequest(
            parameter_name="G",
            end_value=0.5,
            duration=0.0,
            easing=Easing.linear,
        ),
    )
    assert "G" in engine.controlled_params

    await engine.restart()

    assert engine.is_running
    assert engine.controlled_params == {}
    assert engine.active_parameters == ()

    await engine.stop()


# ── keep-alive ───────────────────────────────────────────────────────


async def test_keep_alive_resends_controlled_params() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender, keep_alive_interval=0.05)
    engine.start()

    await engine.tween(
        TweenRequest(
            parameter_name="H",
            end_value=0.8,
            duration=0.0,
            easing=Easing.linear,
            keep_alive=True,
        ),
    )
    initial_count = len(sender.calls)

    # 等待足够时间让 keep-alive 至少触发一次
    await asyncio.sleep(0.15)

    await engine.stop()

    assert len(sender.calls) > initial_count, "keep-alive 应该额外发送了参数值"
    # 验证 keep-alive 发送的是正确的参数
    for _mode, states in sender.calls[initial_count:]:
        for state in states:
            if state.name == "H":
                assert state.value == pytest.approx(0.8)


async def test_keep_alive_does_not_resend_non_keep_alive_params() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender, keep_alive_interval=0.05)
    engine.start()

    await engine.tween(
        TweenRequest(
            parameter_name="NoKeep",
            end_value=0.5,
            duration=0.0,
            easing=Easing.linear,
            keep_alive=False,
        ),
    )
    initial_count = len(sender.calls)

    await asyncio.sleep(0.15)
    await engine.stop()

    # keep_alive=False 的参数不应被保活循环重发
    for _mode, states in sender.calls[initial_count:]:
        for state in states:
            assert state.name != "NoKeep", "keep_alive=False 的参数不应被重发"


# ── 线性插值正确性 ───────────────────────────────────────────────────


async def test_linear_tween_reaches_end_value() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    await engine.tween(
        TweenRequest(
            parameter_name="Interp",
            end_value=1.0,
            start_value=0.0,
            duration=0.1,
            easing=Easing.linear,
            fps=30,
        ),
    )

    # 最后一次发送的值应该接近 end_value
    last_value = None
    for _, states in reversed(sender.calls):
        for state in states:
            if state.name == "Interp":
                last_value = state.value
                break
        if last_value is not None:
            break

    assert last_value is not None
    assert last_value == pytest.approx(1.0, abs=0.05)


async def test_tween_interpolation_is_monotonic_for_linear() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    await engine.tween(
        TweenRequest(
            parameter_name="Mono",
            end_value=1.0,
            start_value=0.0,
            duration=0.15,
            easing=Easing.linear,
            fps=60,
        ),
    )

    values = [state.value for _, states in sender.calls for state in states if state.name == "Mono"]
    assert len(values) >= 2, "应该至少有两次发送"
    for i in range(1, len(values)):
        assert (
            values[i] >= values[i - 1] - 1e-9
        ), f"线性缓动应单调递增: values[{i - 1}]={values[i - 1]}, values[{i}]={values[i]}"


# ── delay ────────────────────────────────────────────────────────────


async def test_tween_with_delay() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    loop = asyncio.get_running_loop()
    start = loop.time()

    await engine.tween(
        TweenRequest(
            parameter_name="Delayed",
            end_value=1.0,
            duration=0.0,
            delay=0.1,
            easing=Easing.linear,
        ),
    )

    elapsed = loop.time() - start
    assert elapsed >= 0.09, "delay 应该至少延迟 0.1 秒"
    assert sender.calls, "delay 后应该发送了值"


# ── add 模式 ─────────────────────────────────────────────────────────


async def test_add_mode_sends_with_add() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    await engine.tween(
        TweenRequest(
            parameter_name="AddParam",
            end_value=0.3,
            duration=0.0,
            easing=Easing.linear,
            mode="add",
        ),
    )

    found_add = False
    for mode, states in sender.calls:
        for state in states:
            if state.name == "AddParam":
                assert mode == "add"
                assert state.mode == "add"
                found_add = True
    assert found_add, "应该以 add 模式发送"


# ── 高优先级抢占 ─────────────────────────────────────────────────────


async def test_high_priority_preempts_running_low_priority() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    # 启动低优先级长缓动
    low_task = asyncio.create_task(
        engine.tween(
            TweenRequest(
                parameter_name="Preempt",
                end_value=0.5,
                duration=5.0,
                easing=Easing.linear,
                priority=10,
            ),
        ),
    )
    await asyncio.sleep(0.05)

    # 高优先级即时设置应该成功
    await engine.tween(
        TweenRequest(
            parameter_name="Preempt",
            end_value=1.0,
            duration=0.0,
            easing=Easing.linear,
            priority=100,
        ),
    )

    # 验证高优先级的值被发送
    found_high = False
    for _, states in sender.calls:
        for state in states:
            if state.name == "Preempt" and state.value == pytest.approx(1.0):
                found_high = True
    assert found_high, "高优先级的值应该被发送"

    low_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await low_task


# ── 并发不同参数 ─────────────────────────────────────────────────────


async def test_concurrent_tweens_on_different_params() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    await asyncio.gather(
        engine.tween(
            TweenRequest(
                parameter_name="Left",
                end_value=0.3,
                duration=0.1,
                easing=Easing.linear,
            ),
        ),
        engine.tween(
            TweenRequest(
                parameter_name="Right",
                end_value=0.7,
                duration=0.1,
                easing=Easing.linear,
            ),
        ),
    )

    left_values = [state.value for _, states in sender.calls for state in states if state.name == "Left"]
    right_values = [state.value for _, states in sender.calls for state in states if state.name == "Right"]
    assert left_values, "Left 参数应有发送记录"
    assert right_values, "Right 参数应有发送记录"
    assert left_values[-1] == pytest.approx(0.3, abs=0.05)
    assert right_values[-1] == pytest.approx(0.7, abs=0.05)


# ── _resolve_easing ──────────────────────────────────────────────────


async def test_resolve_easing_unknown_name_raises() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    with pytest.raises(ValueError, match="未知缓动函数"):
        await engine.tween(
            TweenRequest(
                parameter_name="Bad",
                end_value=1.0,
                start_value=0.0,
                duration=0.1,
                easing="totally_invalid_easing",
            ),
        )


async def test_resolve_easing_callable_is_used_directly() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    custom_called = False

    def custom_easing(t: float) -> float:
        nonlocal custom_called
        custom_called = True
        return t

    await engine.tween(
        TweenRequest(
            parameter_name="Custom",
            end_value=1.0,
            start_value=0.0,
            duration=0.05,
            easing=custom_easing,
        ),
    )

    assert custom_called, "自定义缓动函数应该被调用"


# ── start 重复调用 ───────────────────────────────────────────────────


async def test_start_twice_does_not_create_duplicate_tasks() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    engine.start()
    engine.start()  # 第二次应该是 noop

    assert engine.is_running
    await engine.stop()
    assert not engine.is_running


# ── start_value=None 时从 controlled_params 读取 ────────────────────


async def test_tween_inherits_current_value_when_start_value_is_none() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    # 先设置初始值
    await engine.tween(
        TweenRequest(
            parameter_name="Inherit",
            end_value=0.5,
            duration=0.0,
            easing=Easing.linear,
        ),
    )

    # 再从当前值缓动到 1.0（不指定 start_value）
    await engine.tween(
        TweenRequest(
            parameter_name="Inherit",
            end_value=1.0,
            duration=0.05,
            easing=Easing.linear,
        ),
    )

    values = [state.value for _, states in sender.calls for state in states if state.name == "Inherit"]
    # 第一个缓动发送的值应该是 0.5，后续应从 0.5 开始递增
    assert values[0] == pytest.approx(0.5)
    assert values[-1] == pytest.approx(1.0, abs=0.05)


# ── duration=0 且 start == end 时走即时路径 ──────────────────────────


async def test_immediate_when_start_equals_end() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    await engine.tween(
        TweenRequest(
            parameter_name="Same",
            end_value=0.5,
            start_value=0.5,
            duration=0.1,
            easing=Easing.linear,
        ),
    )

    # start == end 应走即时路径
    assert sender.calls, "即使 start==end 也应发送一次"
    _, states = sender.calls[-1]
    assert states[0].value == pytest.approx(0.5)

"""测试 ParameterTweenEngine

覆盖：
- 缓动按 set/add 模式分批下发
- 高优先级抢占低优先级；低优先级被现有缓动拒绝
- stop() 能清空 active tween 与受控参数
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Literal

import pytest

from livestudio.tween import Easing, ParameterTweenEngine, TweenRequest
from livestudio.tween.models import ControlledParameterState


class _SenderRecorder:
    """记录每次 sender 调用的参数与 mode"""

    def __init__(self) -> None:
        self.calls: list[
            tuple[Literal["set", "add"], list[ControlledParameterState]]
        ] = []

    async def __call__(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        self.calls.append((mode, list(states)))


async def test_immediate_value_sends_end_value() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    await engine.tween(
        TweenRequest(
            parameter_name="MouthOpen",
            end_value=0.7,
            duration=0.0,
            easing=Easing.linear,
        ),
    )

    assert sender.calls, "duration=0 应该立刻发送一次"
    mode, states = sender.calls[-1]
    assert mode == "set"
    assert states[0].name == "MouthOpen"
    assert states[0].value == pytest.approx(0.7)


async def test_low_priority_is_rejected_by_running_high_priority() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    # 长时间运行的高优先级缓动占住参数
    high_task = asyncio.create_task(
        engine.tween(
            TweenRequest(
                parameter_name="EyeOpenLeft",
                end_value=1.0,
                duration=1.0,
                easing=Easing.linear,
                priority=100,
            ),
        ),
    )
    # 让它进入 active 状态
    await asyncio.sleep(0.05)

    # 低优先级即时设置应被拒绝
    await engine.tween(
        TweenRequest(
            parameter_name="EyeOpenLeft",
            end_value=0.0,
            duration=0.0,
            easing=Easing.linear,
            priority=1,
        ),
    )

    high_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await high_task

    # 校验：sender 没有任何把目标值设到 0.0 的调用
    for _, states in sender.calls:
        for state in states:
            if state.name == "EyeOpenLeft":
                assert state.value != 0.0, "低优先级的覆盖不应被发送"


async def test_stop_clears_state() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)
    engine.start()

    await engine.tween(
        TweenRequest(
            parameter_name="MouthOpen",
            end_value=0.5,
            duration=0.0,
            easing=Easing.linear,
        ),
    )
    assert "MouthOpen" in engine.controlled_params

    await engine.stop()

    assert engine.controlled_params == {}
    assert engine.active_parameters == ()
    assert not engine.is_running


async def test_set_and_add_modes_are_dispatched_separately() -> None:
    sender = _SenderRecorder()
    engine = ParameterTweenEngine(sender)

    # 通过内部方法直接检查 _send_parameter_values 的分组，这个用例对应 fix #3
    states = [
        ControlledParameterState(name="A", value=1.0, mode="set"),
        ControlledParameterState(name="B", value=2.0, mode="add"),
        ControlledParameterState(name="C", value=3.0, mode="set"),
    ]
    await engine._send_parameter_values(states)  # noqa: SLF001

    modes = [mode for mode, _ in sender.calls]
    assert modes == ["set", "add"]
    set_payload = sender.calls[0][1]
    add_payload = sender.calls[1][1]
    assert {state.name for state in set_payload} == {"A", "C"}
    assert {state.name for state in add_payload} == {"B"}

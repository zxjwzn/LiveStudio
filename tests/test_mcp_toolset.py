"""MCP 工具集反射与分发测试

验证「通用动词上移基类、标 @tool(builtin=True) 固有化;平台特有工具留在子类」的反射机制:
基类反射把通用动词编入子类实例,universal_tools() / tools() 按 builtin 分流,call() 仍按名分发。
"""

from __future__ import annotations

from typing import Any

import pytest

from livestudio.mcp.constants import TOOL_MARK
from livestudio.mcp.platforms.vtubestudio_toolset import VTubeStudioToolset
from livestudio.mcp.toolset import PlatformToolset

from .mcp_fakes import UNIVERSAL_VERBS, _FakeApp, _FakeToolset


def _tool_meta_map(cls: type) -> dict[str, Any]:
    """类自身直接定义的 @tool 方法 -> 其 _ToolMeta(builtin 标记)。"""

    result: dict[str, Any] = {}
    for name, fn in vars(cls).items():
        meta = getattr(fn, TOOL_MARK, None)
        if meta is not None:
            result[name] = meta
    return result


def test_base_defines_eleven_builtin_verbs() -> None:
    """基类 PlatformToolset 直接定义 11 个 @tool(builtin=True) 通用动词。"""

    metas = _tool_meta_map(PlatformToolset)
    assert set(metas) == UNIVERSAL_VERBS
    assert all(meta.builtin for meta in metas.values())


def test_vtubestudio_keeps_only_native_expressions() -> None:
    """VTubeStudioToolset 只直接定义 3 个 native expressions @tool(非 builtin),不重声明通用动词。"""

    metas = _tool_meta_map(VTubeStudioToolset)
    assert set(metas) == {"list_native_expressions", "set_native_expression", "clear_native_expressions"}
    assert all(not meta.builtin for meta in metas.values())
    # 通用动词不在子类直接定义中(由基类继承)。
    assert not (UNIVERSAL_VERBS & set(metas))


def test_reflection_splits_universal_and_specific() -> None:
    """实例反射:universal_tools() = 11 通用动词;tools() = 平台特有(ping)。"""

    toolset = _FakeToolset(_FakeApp())
    universal_names = {t.name for t in toolset.universal_tools()}
    specific_names = {t.name for t in toolset.tools()}
    assert universal_names == UNIVERSAL_VERBS
    assert specific_names == {"ping"}
    # 两者不重叠。
    assert not (universal_names & specific_names)


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


async def test_play_emotion_validates_argument() -> None:
    """play_emotion 经自动生成的入参模型校验:非法情绪走 app 抛错路径,返回错误串。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    assert await toolset.call("play_emotion", {"emotion": "joy"}) == "已触发情绪：joy。"
    assert app.played == ["joy"]
    assert await toolset.call("play_emotion", {"emotion": "rage"}) == "无法触发情绪：未知情绪: rage"


async def test_play_emotion_forwards_intensity_and_durations() -> None:
    """play_emotion 把 intensity/transition_duration/hold_duration 透传给 app.play_emotion。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    result = await toolset.call(
        "play_emotion",
        {"emotion": "joy", "intensity": 0.5, "transition_duration": 0.3, "hold_duration": 2.0},
    )

    assert result == "已触发情绪：joy。"
    assert app.play_emotion_calls == [
        {
            "emotion": "joy",
            "intensity": 0.5,
            "transition_duration": 0.3,
            "hold_duration": 2.0,
        }
    ]


async def test_play_emotion_defaults_when_params_omitted() -> None:
    """缺省:intensity=1.0,两段时长=None(由 app/控制器回退模型配置)。"""

    app = _FakeApp()
    toolset = _FakeToolset(app)
    await toolset.call("play_emotion", {"emotion": "joy"})

    assert app.play_emotion_calls == [
        {"emotion": "joy", "intensity": 1.0, "transition_duration": None, "hold_duration": None}
    ]

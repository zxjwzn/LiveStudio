"""MCP server 分发测试

验证 list_tools / call_tool:无平台切换元工具;通用动词与特有工具直接可用并注入 runtime_context。
"""
# ruff: noqa: SLF001

from __future__ import annotations

import pytest

from livestudio.mcp import LiveStudioMcpServer, PlatformToolsetRegistration

from .mcp_fakes import UNIVERSAL_VERBS, _FakeApp, _FakeToolset


def _make_server() -> LiveStudioMcpServer:
    return LiveStudioMcpServer(
        platforms=[PlatformToolsetRegistration(name="fake", toolset=_FakeToolset(_FakeApp()))],
    )


def _content_texts(result: object) -> list[str]:
    return [block.text for block in result.content]  # type: ignore[attr-defined]


def test_list_tools_full_catalog() -> None:
    """全表 = 通用动词 + 平台特有(ping);无 list/switch/get_active_platform。"""

    server = _make_server()
    names = {t.name for t in server._list_tools_impl()}
    assert names == UNIVERSAL_VERBS | {"ping"}
    assert "switch_platform" not in names
    assert "list_platforms" not in names
    assert "get_active_platform" not in names


def test_builtin_tools_are_universal_only() -> None:
    """GUI builtin_tools() = 通用动词。"""

    server = _make_server()
    names = {t.name for t in server.builtin_tools()}
    assert names == UNIVERSAL_VERBS


def test_platform_tools_include_all_platform_tools() -> None:
    """GUI platform_tools():每平台含通用+特有(展示层再去重)。"""

    server = _make_server()
    groups = server.platform_tools()
    assert len(groups) == 1
    name, _desc, tools = groups[0]
    assert name == "fake"
    names = {t.name for t in tools}
    assert "ping" in names
    assert UNIVERSAL_VERBS <= names


async def test_call_universal_dispatches_and_injects_context() -> None:
    """通用动词直接可用,结果追加 runtime_context。"""

    server = _make_server()
    result = await server._dispatch_tool("connect", {})
    texts = _content_texts(result)
    assert len(texts) == 2
    assert texts[0] == "已连接平台，当前模型：TestModel。"
    assert texts[1] == "[当前状态] FAKE_RUNTIME_CTX"


async def test_call_specific_dispatches_and_injects_context() -> None:
    """平台特有工具同样注入状态。"""

    server = _make_server()
    result = await server._dispatch_tool("ping", {})
    texts = _content_texts(result)
    assert texts[0] == "pong"
    assert texts[1] == "[当前状态] FAKE_RUNTIME_CTX"


async def test_call_unknown_tool_raises() -> None:
    server = _make_server()
    with pytest.raises(ValueError, match="未知工具"):
        await server._dispatch_tool("no_such_tool", {})


def test_duplicate_tool_name_across_platforms_rejected() -> None:
    """多平台登记时工具名冲突应在构造时报错。"""

    with pytest.raises(ValueError, match="工具名冲突"):
        LiveStudioMcpServer(
            platforms=[
                PlatformToolsetRegistration(name="a", toolset=_FakeToolset(_FakeApp())),
                PlatformToolsetRegistration(name="b", toolset=_FakeToolset(_FakeApp())),
            ],
        )


def test_empty_platforms_rejected() -> None:
    with pytest.raises(ValueError, match="至少需要登记"):
        LiveStudioMcpServer(platforms=[])

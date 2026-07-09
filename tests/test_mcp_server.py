"""MCP server 分发测试

验证 list_tools / call_tool 的可见性与路由:固有 = 元信息3 + 通用动词(恒定可见);
平台特有工具仅 switch 后出现;通用动词与特有工具同走 active 平台 + runtime_context 注入,
元信息无 active、无状态注入。
"""
# ruff: noqa: SLF001  # 测试直调 server 内部分发/元信息方法以验证路由

from __future__ import annotations

import pytest

from livestudio.mcp import LiveStudioMcpServer, PlatformToolsetRegistration
from livestudio.mcp.constants import BUILTIN_NAMES

from .mcp_fakes import UNIVERSAL_VERBS, _FakeApp, _FakeToolset

META_NAMES = {"list_platforms", "switch_platform", "get_active_platform"}


def _make_server() -> LiveStudioMcpServer:
    return LiveStudioMcpServer(
        platforms=[PlatformToolsetRegistration(name="fake", toolset=_FakeToolset(_FakeApp()))],
    )


def _content_texts(result: object) -> list[str]:
    return [block.text for block in result.content]  # type: ignore[attr-defined]


def test_meta_names_match_builtin_names() -> None:
    """BUILTIN_NAMES 恒为元信息3;通用动词不在此集合(走 toolset 反射路径)。"""

    assert BUILTIN_NAMES == META_NAMES
    assert not (BUILTIN_NAMES & UNIVERSAL_VERBS)


def test_list_tools_constant_full_catalog_no_active() -> None:
    """恒定全表:元信息3 + 9 通用动词 + 各平台特有工具(ping),与 active 无关。"""

    server = _make_server()
    names = {t.name for t in server._list_tools_impl()}
    assert names == META_NAMES | UNIVERSAL_VERBS | {"ping"}


async def test_list_tools_constant_across_switch() -> None:
    """工具列表不随 switch 变化(恒定全表),缓存型客户端首次即见全部。"""

    server = _make_server()
    before = {t.name for t in server._list_tools_impl()}
    await server._call_builtin("switch_platform", {"platform": "fake"})
    after = {t.name for t in server._list_tools_impl()}
    assert before == after == META_NAMES | UNIVERSAL_VERBS | {"ping"}


def test_builtin_tools_groups_meta_and_universal() -> None:
    """GUI 用 builtin_tools():元信息3 + 9 通用动词 = 12。"""

    server = _make_server()
    names = {t.name for t in server.builtin_tools()}
    assert names == META_NAMES | UNIVERSAL_VERBS


def test_platform_tools_lists_only_specific() -> None:
    """GUI 用 platform_tools():每平台仅特有工具(ping),通用动词不在其列。"""

    server = _make_server()
    groups = server.platform_tools()
    assert len(groups) == 1
    name, _desc, tools = groups[0]
    assert name == "fake"
    assert {t.name for t in tools} == {"ping"}


async def test_call_meta_list_platforms_no_context() -> None:
    """元信息工具走 _call_builtin:无需 active、不注入状态(单文本块)。"""

    server = _make_server()
    result = await server._dispatch_tool("list_platforms", {})
    texts = _content_texts(result)
    assert len(texts) == 1  # 无 [当前状态] 注入
    assert "fake" in texts[0]


async def test_call_universal_before_switch_raises() -> None:
    """通用动词未 switch 时调用报「尚未选择平台」。"""

    server = _make_server()
    with pytest.raises(ValueError, match="尚未选择平台"):
        await server._dispatch_tool("connect", {})


async def test_call_universal_after_switch_dispatches_and_injects_context() -> None:
    """switch 后通用动词走 active 平台,结果追加 runtime_context 状态块。"""

    server = _make_server()
    await server._dispatch_tool("switch_platform", {"platform": "fake"})

    result = await server._dispatch_tool("connect", {})
    texts = _content_texts(result)
    assert len(texts) == 2  # 工具返回 + [当前状态] 注入
    assert texts[0] == "已连接平台，当前模型：TestModel。"
    assert texts[1] == "[当前状态] FAKE_RUNTIME_CTX"


async def test_call_specific_after_switch_dispatches_and_injects_context() -> None:
    """平台特有工具与通用动词同走 active 路径,同样注入状态。"""

    server = _make_server()
    await server._dispatch_tool("switch_platform", {"platform": "fake"})

    result = await server._dispatch_tool("ping", {})
    texts = _content_texts(result)
    assert texts[0] == "pong"
    assert texts[1] == "[当前状态] FAKE_RUNTIME_CTX"


async def test_get_active_platform_reflects_switch() -> None:
    """get_active_platform 在 switch 前后返回 null / 平台名。"""

    server = _make_server()
    before = await server._dispatch_tool("get_active_platform", {})
    assert "null" in _content_texts(before)[0]

    await server._dispatch_tool("switch_platform", {"platform": "fake"})
    after = await server._dispatch_tool("get_active_platform", {})
    assert "fake" in _content_texts(after)[0]

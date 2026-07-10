"""GUI 异步工具测试

重点:Windows proactor 套接字拆除时 _call_connection_lost 的 socket.shutdown(SHUT_RDWR)
会对已 RST 的连接抛 ConnectionResetError,asyncio 当「Exception in callback」记 ERROR。
验证 is_benign_proactor_connection_reset / proactor_reset_filter_handler 精准识别并静默
此类良性噪音,且不误伤其他异常。
"""

# ruff: noqa: SLF001  # 测试直调 async_utils 内部分发以验证路由

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

from livestudio.gui.core.async_utils import (
    is_benign_proactor_connection_reset,
    proactor_reset_filter_handler,
    silence_proactor_connection_reset_on_close,
)


def _ctx(message: str, exc: BaseException) -> dict[str, Any]:
    """构造 asyncio call_exception_handler 的 context 字典。"""

    return {"message": message, "exception": exc}


def test_reset_from_call_connection_lost_is_benign() -> None:
    """用户实测报错形态:_call_connection_lost(None) + ConnectionResetError,判为良性。"""

    ctx = _ctx(
        "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
        ConnectionResetError("[WinError 10054] 远程主机强迫关闭了一个现有的连接。"),
    )
    assert is_benign_proactor_connection_reset(ctx)


def test_connection_aborted_from_call_connection_lost_is_benign() -> None:
    """ConnectionAbortedError(WinError 10053)同为套接字拆除良性噪音。"""

    ctx = _ctx(
        "Exception in callback _ProactorBasePipeTransport._call_connection_lost(None)",
        ConnectionAbortedError("[WinError 10053]"),
    )
    assert is_benign_proactor_connection_reset(ctx)


def test_other_exception_not_benign() -> None:
    """非连接重置异常(如 ValueError)不静默,交默认处理器。"""

    assert not is_benign_proactor_connection_reset(_ctx("Exception in callback cb()", ValueError("boom")))


def test_reset_outside_call_connection_lost_not_benign() -> None:
    """ConnectionResetError 出现在业务回调里(非 _call_connection_lost)不静默--可能是真问题。"""

    ctx = _ctx("Exception in callback my_app_callback()", ConnectionResetError("x"))
    assert not is_benign_proactor_connection_reset(ctx)


def test_filter_handler_suppresses_benign_delegates_rest() -> None:
    """处理器对良性连接重置静默,其余异常委托给 loop 默认处理器。"""

    loop = asyncio.new_event_loop()
    try:
        delegated: list[dict[str, Any]] = []
        loop.default_exception_handler = delegated.append  # type: ignore[method-assign]
        handler = proactor_reset_filter_handler(loop)

        benign = _ctx("... _call_connection_lost(None)", ConnectionResetError("x"))
        serious = _ctx("Exception in callback cb()", ValueError("boom"))

        handler(loop, benign)  # 静默,不委托
        handler(loop, serious)  # 委托默认处理器
        assert delegated == [serious]
    finally:
        loop.close()


@pytest.mark.skipif(os.name != "nt", reason="proactor 噪音屏蔽仅 Windows 需要")
def test_silencer_installs_handler_on_windows() -> None:
    """Windows 上 silence_proactor_connection_reset_on_close 装上异常处理器。"""

    loop = asyncio.new_event_loop()
    try:
        assert loop.get_exception_handler() is None
        silence_proactor_connection_reset_on_close(loop)
        assert loop.get_exception_handler() is not None
    finally:
        loop.close()


@pytest.mark.skipif(os.name == "nt", reason="非 Windows 应为空操作")
def test_silencer_noop_off_windows() -> None:
    """非 Windows 无 proactor,装屏蔽为空操作(不装处理器)。"""

    loop = asyncio.new_event_loop()
    try:
        silence_proactor_connection_reset_on_close(loop)
        assert loop.get_exception_handler() is None
    finally:
        loop.close()

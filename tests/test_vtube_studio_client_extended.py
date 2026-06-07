"""扩展 VTubeStudioClient 测试

覆盖：
- _parse_response: requestID 不匹配、APIError、无效 JSON、非文本
- _fail_pending_requests: 所有挂起请求被异常终止
- event handler 注册 / 移除 / has_event_handlers
- _dispatch_event: 无 handler 时静默
- disconnect 后 is_connected 为 False
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
import pytest
from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.clients.vtube_studio.config import VTubeStudioConfig
from livestudio.clients.vtube_studio.errors import (
    APIError,
    ResponseError,
    VTubeStudioConnectionError,
)
from livestudio.clients.vtube_studio.models import APIStateResponse


def _make_client() -> VTubeStudioClient:
    config = VTubeStudioConfig()
    return VTubeStudioClient(
        config=config,
        plugin_info=config.plugin,
    )


# ── _parse_response ──────────────────────────────────────────────────


def test_parse_response_non_string_raises() -> None:
    client = _make_client()
    with pytest.raises(ResponseError, match="不是文本消息"):
        client._parse_response(12345, "req-1", APIStateResponse)


def test_parse_response_invalid_json_raises() -> None:
    client = _make_client()
    with pytest.raises(ResponseError, match="不是有效 JSON"):
        client._parse_response("not json {{{", "req-1", APIStateResponse)


def test_parse_response_request_id_mismatch_raises() -> None:
    client = _make_client()
    payload = json.dumps({
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "requestID": "wrong-id",
        "messageType": "APIStateResponse",
        "data": {},
    })
    with pytest.raises(ResponseError, match="requestID 不匹配"):
        client._parse_response(payload, "correct-id", APIStateResponse)


def test_parse_response_api_error_raises() -> None:
    client = _make_client()
    payload = json.dumps({
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "timestamp": 1700000000000,
        "requestID": "req-1",
        "messageType": "APIError",
        "data": {
            "errorID": 1,
            "message": "Something went wrong",
        },
    })
    with pytest.raises(APIError) as exc_info:
        client._parse_response(payload, "req-1", APIStateResponse)
    assert exc_info.value.error_id == 1


# ── event handler 注册 / 移除 ────────────────────────────────────────


def test_add_and_remove_event_handler() -> None:
    client = _make_client()

    async def handler(event: Any) -> None:
        pass

    client.add_event_handler("TestEvent", handler)
    assert client.has_event_handlers("TestEvent")

    client.remove_event_handler("TestEvent", handler)
    assert not client.has_event_handlers("TestEvent")


def test_remove_nonexistent_handler_is_noop() -> None:
    client = _make_client()

    async def handler(event: Any) -> None:
        pass

    # 移除不存在的事件名
    client.remove_event_handler("NoSuchEvent", handler)

    # 移除不存在的 handler
    async def other_handler(event: Any) -> None:
        pass

    client.add_event_handler("TestEvent", handler)
    client.remove_event_handler("TestEvent", other_handler)
    assert client.has_event_handlers("TestEvent")


def test_has_event_handlers_false_when_no_handlers() -> None:
    client = _make_client()
    assert not client.has_event_handlers("NonExistent")


# ── _fail_pending_requests ───────────────────────────────────────────


def test_fail_pending_requests_sets_exception_on_all() -> None:
    client = _make_client()
    loop = asyncio.new_event_loop()
    try:
        f1 = loop.create_future()
        f2 = loop.create_future()
        client._pending_requests["a"] = f1
        client._pending_requests["b"] = f2

        error = VTubeStudioConnectionError("test disconnect")
        client._fail_pending_requests(error)

        assert f1.done()
        assert f2.done()
        assert client._pending_requests == {}

        with pytest.raises(VTubeStudioConnectionError):
            f1.result()
        with pytest.raises(VTubeStudioConnectionError):
            f2.result()
    finally:
        loop.close()


def test_fail_pending_requests_skips_already_done() -> None:
    client = _make_client()
    loop = asyncio.new_event_loop()
    try:
        f1 = loop.create_future()
        f1.set_result("already done")
        client._pending_requests["a"] = f1

        error = VTubeStudioConnectionError("test")
        client._fail_pending_requests(error)

        assert f1.result() == "already done"
    finally:
        loop.close()


# ── is_connected ─────────────────────────────────────────────────────


def test_is_connected_false_initially() -> None:
    client = _make_client()
    assert not client.is_connected


# ── _dispatch_event 无 handler 时静默 ────────────────────────────────


async def test_dispatch_event_no_handlers_is_silent() -> None:
    client = _make_client()
    # 不应抛异常
    await client._dispatch_event("UnknownEvent", '{"messageType":"UnknownEvent"}')

"""测试 VTube Studio 服务层的自动重连机制

覆盖：
- 首次连接失败后重试直到成功
- 认证失败等非连接错误直接抛出不重试
- 重连后成功标记 started
"""

# ruff: noqa: SLF001

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from livestudio.clients.vtube_studio.errors import (
    AuthenticationError,
    VTubeStudioConnectionError,
)
from livestudio.services.platforms.vtubestudio import VTubeStudio


async def test_start_retries_on_connection_error_until_success() -> None:
    """连接失败时自动重试，成功后返回"""
    platform = VTubeStudio()
    await platform._ensure_dependencies_built()

    connect_calls = 0

    async def _failing_connect() -> None:
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls < 3:
            raise VTubeStudioConnectionError("connection refused")

    with patch.object(platform, "connect", side_effect=_failing_connect):
        with patch.object(platform, "authenticate", AsyncMock()):
            with patch("asyncio.sleep", AsyncMock()):
                await platform.start()

    assert platform.is_started
    assert connect_calls == 3


async def test_start_raises_non_connection_errors_immediately() -> None:
    """认证失败等非连接错误不重试，直接抛出"""
    platform = VTubeStudio()
    await platform._ensure_dependencies_built()

    async def _failing_authenticate() -> None:
        raise AuthenticationError("token invalid")

    with patch.object(platform, "connect", AsyncMock()):
        with patch.object(platform, "authenticate", side_effect=_failing_authenticate):
            with patch("asyncio.sleep", AsyncMock()):
                with pytest.raises(AuthenticationError, match="token invalid"):
                    await platform.start()

    assert not platform.is_started


async def test_start_stops_tween_and_disconnects_on_non_connection_error() -> None:
    """非连接错误抛出前经 Mixin 回滚清理 tween 和客户端连接"""
    platform = VTubeStudio()
    await platform._ensure_dependencies_built()

    async def _failing_authenticate() -> None:
        raise RuntimeError("unexpected error")

    with patch.object(platform, "connect", AsyncMock()):
        with patch.object(platform, "authenticate", side_effect=_failing_authenticate):
            with patch.object(platform.config_manager, "save", AsyncMock()):
                with patch.object(platform.tween, "stop", AsyncMock()) as mock_stop:
                    with patch.object(platform.client, "disconnect", AsyncMock()) as mock_disconnect:
                        with patch("asyncio.sleep", AsyncMock()):
                            with pytest.raises(RuntimeError, match="unexpected error"):
                                await platform.start()

    mock_stop.assert_awaited_once()
    mock_disconnect.assert_awaited_once()


async def test_start_is_idempotent_after_success() -> None:
    """start() 成功后再次调用直接返回，不重复连接"""
    platform = VTubeStudio()
    await platform._ensure_dependencies_built()

    with patch.object(platform, "connect", AsyncMock()) as mock_connect:
        with patch.object(platform, "authenticate", AsyncMock()):
            await platform.start()
            first_call_count = mock_connect.call_count

            await platform.start()  # 二次调用

            assert mock_connect.call_count == first_call_count

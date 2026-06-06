"""测试 VTube Studio 平台服务能不能正常开始和结束"""

from __future__ import annotations

from typing import cast

import pytest

from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.services.platforms.vtubestudio import VTubeStudio


class _DisconnectRecorder:
    def __init__(self) -> None:
        self.disconnect_calls = 0

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


async def test_vtube_studio_start_disconnects_when_authentication_fails() -> None:
    platform = VTubeStudio()
    client = _DisconnectRecorder()
    platform._initialized = True  # noqa: SLF001
    platform._client = cast(VTubeStudioClient, client)  # noqa: SLF001

    async def connect() -> None:
        pass

    async def authenticate() -> None:
        raise RuntimeError("auth failed")

    platform.connect = connect  # type: ignore[method-assign]
    platform.authenticate = authenticate  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="auth failed"):
        await platform.start()

    assert client.disconnect_calls == 1
    assert not platform.is_started
    assert not platform.tween.is_running

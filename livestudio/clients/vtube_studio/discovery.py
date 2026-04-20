"""用于处理 VTube Studio API 广播的 UDP 发现辅助工具。"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator

from pydantic import ValidationError

from .config import VTubeStudioConfig
from .errors import DiscoveryError
from .models import VTubeStudioAPIStateBroadcast


class VTubeStudioDiscovery:
    """监听 VTube Studio 的 UDP 广播。"""

    def __init__(self, config: VTubeStudioConfig) -> None:
        self._config = config

    async def discover_once(self, timeout: float | None = None) -> VTubeStudioAPIStateBroadcast:
        effective_timeout = timeout or self._config.discovery_timeout
        async for broadcast in self.listen(timeout=effective_timeout, max_messages=1):
            return broadcast
        raise DiscoveryError("在超时时间内未收到 VTube Studio UDP 广播")

    async def listen(
        self,
        timeout: float | None = None,
        max_messages: int | None = None,
    ) -> AsyncIterator[VTubeStudioAPIStateBroadcast]:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind(("", self._config.discovery_port))
        except OSError as exc:
            sock.close()
            raise DiscoveryError(f"无法绑定 UDP 端口 {self._config.discovery_port}") from exc

        try:
            received = 0
            while max_messages is None or received < max_messages:
                try:
                    data, _ = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, self._config.udp_buffer_size),
                        timeout=timeout or self._config.discovery_timeout,
                    )
                except TimeoutError as exc:
                    raise DiscoveryError("等待 VTube Studio UDP 广播超时") from exc

                try:
                    yield VTubeStudioAPIStateBroadcast.model_validate_json(data.decode("utf-8"))
                except (UnicodeDecodeError, ValidationError) as exc:
                    raise DiscoveryError("收到的 UDP 广播无法解析") from exc
                received += 1
        finally:
            sock.close()
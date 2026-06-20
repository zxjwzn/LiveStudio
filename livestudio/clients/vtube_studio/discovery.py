"""用来接收 VTube Studio 广播的 UDP 小工具"""

import asyncio
import contextlib
import socket
from collections.abc import AsyncGenerator

from pydantic import ValidationError

from .config import VTubeStudioConfig
from .errors import DiscoveryError
from .models import VTubeStudioAPIStateBroadcast


class VTubeStudioDiscovery:
    """监听 VTube Studio 发出来的 UDP 广播"""

    def __init__(self, config: VTubeStudioConfig) -> None:
        self._config = config

    async def discover_once(
        self,
        timeout: float | None = None,
    ) -> VTubeStudioAPIStateBroadcast:
        effective_timeout = timeout or self._config.discovery_timeout
        async with contextlib.aclosing(
            self.listen(timeout=effective_timeout, max_messages=1),
        ) as broadcasts:
            async for broadcast in broadcasts:
                return broadcast
        raise DiscoveryError("在超时时间内未收到 VTube Studio UDP 广播")

    async def listen(
        self,
        timeout: float | None = None,
        max_messages: int | None = None,
    ) -> AsyncGenerator[VTubeStudioAPIStateBroadcast, None]:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind(("", self._config.discovery_port))
        except OSError as exc:
            sock.close()
            raise DiscoveryError(
                f"无法绑定 UDP 端口 {self._config.discovery_port}",
            ) from exc

        try:
            received = 0
            while max_messages is None or received < max_messages:
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, self._config.udp_buffer_size),
                        timeout=timeout or self._config.discovery_timeout,
                    )
                except TimeoutError as exc:
                    raise DiscoveryError("等待 VTube Studio UDP 广播超时") from exc

                try:
                    broadcast = VTubeStudioAPIStateBroadcast.model_validate_json(
                        data.decode("utf-8"),
                    )
                except (UnicodeDecodeError, ValidationError) as exc:
                    raise DiscoveryError("收到的 UDP 广播无法解析") from exc
                # 广播负载本身不含主机地址，真实 IP 取自 UDP 数据包源地址
                broadcast.source_host = addr[0] if addr else None
                yield broadcast
                received += 1
        finally:
            sock.close()

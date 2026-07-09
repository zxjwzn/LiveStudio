"""用来接收 VTube Studio 广播的 UDP 小工具"""

import asyncio
import contextlib
import socket
from collections.abc import AsyncGenerator, Callable

from pydantic import ValidationError

from .config import VTubeStudioConfig
from .errors import DiscoveryError
from .models import VTubeStudioAPIStateBroadcast


class VTubeStudioDiscovery:
    """监听 VTube Studio 发出来的 UDP 广播"""

    def __init__(self, config_provider: Callable[[], VTubeStudioConfig]) -> None:
        # 持有返回最新配置的 provider 而非配置快照：discovery 在服务构造期就建立，
        # 但配置由 config_manager.load() 在 start 时替换为新对象，故每次监听都重新读取，
        # 避免捕获构造期的陈旧默认值。
        self._config_provider = config_provider

    @property
    def _config(self) -> VTubeStudioConfig:
        return self._config_provider()

    def _bind_udp_socket(self) -> socket.socket:
        """建立并绑定接收广播的 UDP 套接字（SO_REUSEADDR，允许多个监听者共存）。

        绑定失败（端口被独占）抛 DiscoveryError，由调用方决定如何呈现。
        """

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
        return sock

    async def discover_once(
        self,
        timeout: float | None = None,
    ) -> VTubeStudioAPIStateBroadcast:
        """拿到第一条广播即返回；超时抛 DiscoveryError。"""

        effective_timeout = timeout or self._config.discovery_timeout
        async with contextlib.aclosing(
            self.listen(timeout=effective_timeout, max_messages=1),
        ) as broadcasts:
            async for broadcast in broadcasts:
                return broadcast
        raise DiscoveryError("在超时时间内未收到 VTube Studio UDP 广播")

    async def discover_all(
        self,
        timeout: float | None = None,
    ) -> list[VTubeStudioAPIStateBroadcast]:
        """在固定时间窗内收集所有 VTS 广播，按 (源主机, 端口) 去重后返回。

        与 discover_once（拿到第一条即返回）不同：本方法持续监听整个窗口以发现多个实例，
        到期自然结束。用于 GUI 的 LAN 搜索——VTS 在线时会持续广播，若像 listen 那样靠
        「下一条广播超时」判定结束，生成器永不返回（每条 per-message 超时都被下一条广播
        打断），导致搜索卡在「搜索中…」。改用墙钟窗口（loop.time 截止时刻）保证必然终止。

        窗口内未收到任何广播时返回空列表（非异常），由调用方按「未发现」处理；无法解析
        的包被跳过，不影响窗口内其余实例的发现。
        """

        window = timeout if timeout is not None else self._config.discovery_timeout
        loop = asyncio.get_running_loop()
        sock = self._bind_udp_socket()
        deadline = loop.time() + window
        seen: dict[tuple[str, int], VTubeStudioAPIStateBroadcast] = {}
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, self._config.udp_buffer_size),
                        timeout=remaining,
                    )
                except TimeoutError:
                    break
                try:
                    broadcast = VTubeStudioAPIStateBroadcast.model_validate_json(
                        data.decode("utf-8"),
                    )
                except (UnicodeDecodeError, ValidationError):
                    continue
                # 广播负载本身不含主机地址，真实 IP 取自 UDP 数据包源地址
                broadcast.source_host = addr[0] if addr else None
                if broadcast.source_host is not None:
                    seen.setdefault(
                        (broadcast.source_host, broadcast.data.port),
                        broadcast,
                    )
        finally:
            sock.close()
        return list(seen.values())

    async def listen(
        self,
        timeout: float | None = None,
        max_messages: int | None = None,
    ) -> AsyncGenerator[VTubeStudioAPIStateBroadcast, None]:
        """流式监听广播：每条最多等 per-message timeout，收到 max_messages 条或超时停止。

        注意 per-message 超时语义：max_messages=None 时仅靠「下一条广播超时」结束，
        活跃 VTS 持续广播会让它永不返回。需「收集窗口内全部实例」请用 discover_all。
        """

        loop = asyncio.get_running_loop()
        sock = self._bind_udp_socket()
        effective_timeout = timeout or self._config.discovery_timeout

        try:
            received = 0
            while max_messages is None or received < max_messages:
                try:
                    data, addr = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, self._config.udp_buffer_size),
                        timeout=effective_timeout,
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

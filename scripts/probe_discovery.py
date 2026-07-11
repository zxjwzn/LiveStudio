"""直接调用 VTubeStudioDiscovery 验证 LAN 发现，并确认 discover_all 修复了 GUI 卡死。

四组测试：
  A. 真实端口 47779 上 discover_once -- 证明底层发现本身有效（能抓真实 VTS 广播）。
  B. 模拟端口 discover_once -- 证明 绑定->recvfrom->解析->yield 全链路有效。
  C. 旧路径复现：listen(max_messages=None) + 持续广播 -> 永不返回（GUI 卡死的根因）。
  D. 新路径验证：discover_all + 持续广播 -> 在窗口内必然终止并去重。
  E. discover_all 真实端口 -> 终止并发现真实实例。
"""

import asyncio
import contextlib
import json
import socket

from livestudio.clients.vtube_studio.config import VTubeStudioConfig
from livestudio.clients.vtube_studio.discovery import VTubeStudioDiscovery
from livestudio.clients.vtube_studio.errors import DiscoveryError


def make_config(port: int, timeout: float = 2.0) -> VTubeStudioConfig:
    return VTubeStudioConfig(discovery_port=port, discovery_timeout=timeout)


def fake_broadcast_payload(port: int = 8001) -> bytes:
    payload = {
        "apiName": "VTubeStudioPublicAPI",
        "apiVersion": "1.0",
        "timestamp": 0,
        "messageType": "VTubeStudioAPIStateBroadcast",
        "requestID": "test-request-id",
        "data": {
            "active": True,
            "port": port,
            "instanceID": "test-instance-123",
            "windowTitle": "Test VTS",
        },
    }
    return json.dumps(payload).encode("utf-8")


async def fake_broadcaster(port: int, count: int, interval: float) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    raw = fake_broadcast_payload()
    await asyncio.sleep(0.3)
    for _ in range(count):
        s.sendto(raw, ("127.0.0.1", port))
        await asyncio.sleep(interval)
    s.close()


async def collect_all_legacy(discovery: VTubeStudioDiscovery, timeout: float) -> list:
    """复刻旧 listen_for_api：listen(max_messages=None) 收集全部。"""
    async with contextlib.aclosing(
        discovery.listen(timeout=timeout, max_messages=None),
    ) as broadcasts:
        return [b async for b in broadcasts]


async def timed(_label: str, coro) -> None:
    loop = asyncio.get_running_loop()
    start = loop.time()
    await coro
    print(f"    耗时 {loop.time() - start:.2f}s")


async def test_a_real_port_discover_once() -> None:
    print("[A] 真实端口 47779 discover_once（超时 3s）...")
    cfg = make_config(47779, timeout=3.0)
    discovery = VTubeStudioDiscovery(lambda: cfg)
    try:
        b = await discovery.discover_once(timeout=3.0)
        print(f"    成功: host={b.source_host} port={b.data.port} "
              f"instance={b.data.instance_id} title={b.data.window_title}")
    except DiscoveryError as e:
        print(f"    DiscoveryError（本机未运行 VTS）: {e}")


async def test_b_simulated_discover_once() -> None:
    print("[B] 模拟端口 47890 discover_once（假广播源）...")
    port = 47890
    cfg = make_config(port, timeout=3.0)
    discovery = VTubeStudioDiscovery(lambda: cfg)
    asyncio.create_task(fake_broadcaster(port, count=3, interval=0.3))
    b = await discovery.discover_once(timeout=3.0)
    assert b.data.instance_id == "test-instance-123", b.data.instance_id
    assert b.source_host == "127.0.0.1", b.source_host
    print(f"    全链路有效: host={b.source_host} port={b.data.port}")


async def test_c_legacy_hang() -> None:
    print("[C] 旧路径 listen(max_messages=None) + 持续广播（预期复现卡死）...")
    port = 47891
    cfg = make_config(port, timeout=2.0)
    discovery = VTubeStudioDiscovery(lambda: cfg)
    asyncio.create_task(fake_broadcaster(port, count=15, interval=0.3))
    try:
        await asyncio.wait_for(collect_all_legacy(discovery, timeout=2.0), timeout=5.0)
        print("    未复现（异常：旧路径应卡死）")
    except asyncio.TimeoutError:
        print("    复现成功: 旧路径在持续广播下永不返回")


async def test_d_discover_all_no_hang() -> None:
    print("[D] 新路径 discover_all + 持续广播（预期窗口内终止并去重）...")
    port = 47892
    cfg = make_config(port, timeout=2.0)
    discovery = VTubeStudioDiscovery(lambda: cfg)
    asyncio.create_task(fake_broadcaster(port, count=15, interval=0.3))

    async def run() -> None:
        result = await asyncio.wait_for(discovery.discover_all(timeout=2.0), timeout=5.0)
        assert len(result) == 1, f"应去重为 1 个实例，实得 {len(result)}"
        b = result[0]
        assert b.source_host == "127.0.0.1" and b.data.instance_id == "test-instance-123"
        print(f"    修复有效: 窗口内终止，去重得 1 实例 host={b.source_host}")

    await timed("[D]", run())


async def test_e_discover_all_real() -> None:
    print("[E] 真实端口 47779 discover_all（窗口 2s，预期发现真实实例并终止）...")
    cfg = make_config(47779, timeout=2.0)
    discovery = VTubeStudioDiscovery(lambda: cfg)

    async def run() -> None:
        result = await discovery.discover_all(timeout=2.0)
        if not result:
            print("    窗口内未发现实例（本机未运行 VTS）")
            return
        for b in result:
            print(f"    发现: host={b.source_host} port={b.data.port} instance={b.data.instance_id}")

    await timed("[E]", run())


async def test_f_discover_all_empty_terminates() -> None:
    print("[F] discover_all 无广播时（预期窗口到期返回空列表，不抛错）...")
    port = 47893
    cfg = make_config(port, timeout=1.5)
    discovery = VTubeStudioDiscovery(lambda: cfg)

    async def run() -> None:
        result = await asyncio.wait_for(discovery.discover_all(timeout=1.5), timeout=4.0)
        assert result == [], f"应返回空列表，实得 {result}"
        print("    空窗口返回 []（非异常）")

    await timed("[F]", run())


async def main() -> None:
    await test_a_real_port_discover_once()
    await test_b_simulated_discover_once()
    await test_c_legacy_hang()
    await test_d_discover_all_no_hang()
    await test_e_discover_all_real()
    await test_f_discover_all_empty_terminates()


if __name__ == "__main__":
    asyncio.run(main())

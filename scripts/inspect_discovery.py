"""探查单个 VTS 实例是否产生多个 (host, port) 候选，确认去重键。"""
import asyncio
from livestudio.clients.vtube_studio.config import VTubeStudioConfig
from livestudio.clients.vtube_studio.discovery import VTubeStudioDiscovery
from livestudio.clients.vtube_studio.errors import DiscoveryError

async def main():
    cfg = VTubeStudioConfig(discovery_port=47779, discovery_timeout=3.0)
    d = VTubeStudioDiscovery(lambda: cfg)
    try:
        result = await d.discover_all(timeout=3.0)
    except DiscoveryError as e:
        print(f"DiscoveryError: {e}")
        return
    print(f"discover_all 返回 {len(result)} 条（按 (host,port) 去重后）")
    for b in result:
        print(f"  host={b.source_host} port={b.data.port} instance={b.data.instance_id} title={b.data.window_title}")
    by_inst = {}
    for b in result:
        by_inst.setdefault(b.data.instance_id, b)
    print(f"按 instance_id 去重后: {len(by_inst)} 个实例")

asyncio.run(main())

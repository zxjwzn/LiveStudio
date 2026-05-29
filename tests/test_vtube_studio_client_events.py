"""VTubeStudioClient event dispatch behavior tests."""

from __future__ import annotations

import asyncio
import json

from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.clients.vtube_studio.config import (
    VTubeStudioConfig,
    VTubeStudioPluginInfo,
)
from livestudio.clients.vtube_studio.models import VTSEventEnvelope


def _make_client() -> VTubeStudioClient:
    return VTubeStudioClient(
        config=VTubeStudioConfig(),
        plugin_info=VTubeStudioPluginInfo(
            plugin_name="LiveStudio",
            plugin_developer="Zaxpris",
        ),
    )


def _event_payload(message_type: str = "TestEvent") -> str:
    return json.dumps(
        {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "timestamp": 1,
            "messageType": message_type,
            "requestID": "event",
            "data": {"counter": 1},
        },
    )


async def test_event_dispatch_does_not_wait_for_async_handler() -> None:
    client = _make_client()
    started = asyncio.Event()
    release = asyncio.Event()
    finished = False

    async def slow_handler(event: VTSEventEnvelope) -> None:
        nonlocal finished
        assert event.message_type == "TestEvent"
        started.set()
        await release.wait()
        finished = True

    client.add_event_handler("TestEvent", slow_handler)

    await client._dispatch_event("TestEvent", _event_payload())  # noqa: SLF001

    await asyncio.wait_for(started.wait(), timeout=0.5)
    assert not finished

    release.set()
    tasks = tuple(client._event_tasks)  # noqa: SLF001
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=0.5)
    assert finished


async def test_disconnect_cancels_event_tasks_without_connection() -> None:
    client = _make_client()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow_handler(event: VTSEventEnvelope) -> None:
        _ = event
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    client.add_event_handler("TestEvent", slow_handler)
    await client._dispatch_event("TestEvent", _event_payload())  # noqa: SLF001
    await asyncio.wait_for(started.wait(), timeout=0.5)

    await client.disconnect()

    await asyncio.wait_for(cancelled.wait(), timeout=0.5)

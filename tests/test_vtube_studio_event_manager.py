"""测试 VTube Studio 事件监听功能链路"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.clients.vtube_studio.event_manager import VTSEventManager
from livestudio.clients.vtube_studio.models import VTSEventEnvelope

Handler = Callable[[VTSEventEnvelope], Awaitable[None] | None]


async def _call_handler(handler: Handler, event: VTSEventEnvelope) -> None:
    result = handler(event)
    if result is not None:
        await result


def _event(counter: int) -> VTSEventEnvelope:
    return VTSEventEnvelope.model_validate(
        {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "timestamp": counter,
            "messageType": "TestEvent",
            "requestID": f"event-{counter}",
            "data": {"counter": counter},
        },
    )


class _EventClient:
    def __init__(self) -> None:
        self.handlers: dict[str, list[Handler]] = {}

    def add_event_handler(self, event_name: str, handler: Handler) -> None:
        self.handlers.setdefault(event_name, []).append(handler)

    def remove_event_handler(self, event_name: str, handler: Handler) -> None:
        self.handlers[event_name].remove(handler)

    def has_event_handlers(self, event_name: str) -> bool:
        return bool(self.handlers.get(event_name))


async def test_event_manager_listener_receives_events_and_can_be_removed() -> None:
    client = _EventClient()
    manager = VTSEventManager(cast(VTubeStudioClient, client), queue_size=2)

    listener = manager.create_listener("TestEvent")
    assert manager.has_handlers("TestEvent")

    handler = listener.handler
    assert handler is not None
    await _call_handler(handler, _event(1))

    event = await listener.next_event(timeout=0.5)
    assert event.timestamp == 1

    manager.remove_listener(listener)
    assert not manager.has_handlers("TestEvent")


async def test_event_manager_listener_keeps_latest_events_when_queue_is_full() -> None:
    client = _EventClient()
    manager = VTSEventManager(cast(VTubeStudioClient, client), queue_size=1)
    listener = manager.create_listener("TestEvent")
    handler = listener.handler
    assert handler is not None

    await _call_handler(handler, _event(1))
    await _call_handler(handler, _event(2))

    event = await listener.next_event(timeout=0.5)
    assert event.timestamp == 2
    assert listener.empty()

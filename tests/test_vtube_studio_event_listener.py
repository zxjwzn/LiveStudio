"""测试 VTube Studio 事件监听功能链路"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.clients.vtube_studio.event_listener import VTSEventListener
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

    def create_event_listener(
        self,
        event_name: str,
        *,
        queue_size: int,
    ) -> VTSEventListener:
        listener = VTSEventListener(event_name=event_name, queue_size=queue_size)

        async def _queue_handler(event: VTSEventEnvelope) -> None:
            await listener.push(event)

        listener.handler = _queue_handler
        self.add_event_handler(event_name, _queue_handler)
        return listener

    def remove_event_listener(self, listener: VTSEventListener) -> None:
        handler = listener.handler
        if handler is not None:
            self.remove_event_handler(listener.event_name, handler)


async def test_client_event_listener_receives_events_and_can_be_removed() -> None:
    client = _EventClient()
    client = cast(VTubeStudioClient, client)

    listener = client.create_event_listener("TestEvent", queue_size=2)
    assert client.has_event_handlers("TestEvent")

    handler = listener.handler
    assert handler is not None
    await _call_handler(handler, _event(1))

    event = await listener.next_event(timeout=0.5)
    assert event.timestamp == 1

    client.remove_event_listener(listener)
    assert not client.has_event_handlers("TestEvent")


async def test_client_event_listener_keeps_latest_events_when_queue_is_full() -> None:
    client = _EventClient()
    client = cast(VTubeStudioClient, client)
    listener = client.create_event_listener("TestEvent", queue_size=1)
    handler = listener.handler
    assert handler is not None

    await _call_handler(handler, _event(1))
    await _call_handler(handler, _event(2))

    event = await listener.next_event(timeout=0.5)
    assert event.timestamp == 2
    assert listener.empty()

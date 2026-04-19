"""High-level event subscription manager for VTube Studio."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .client import VTubeStudioClient
from .event_listener import VTSEventListener
from .models import (
    EventSubscriptionRequest,
    EventSubscriptionResponse,
    VTSEventEnvelope,
)

ListenerHandler = Callable[[VTSEventEnvelope], Awaitable[None] | None]


class VTSEventManager:
    """管理事件订阅、回调与队列监听。"""

    def __init__(self, client: VTubeStudioClient, queue_size: int) -> None:
        self._client = client
        self._queue_size = queue_size

    async def subscribe(self, request: EventSubscriptionRequest) -> EventSubscriptionResponse:
        return await self._client.subscribe_event(request)

    async def unsubscribe(self, event_name: str | None = None) -> EventSubscriptionResponse:
        return await self._client.unsubscribe_event(event_name)

    def add_handler(self, event_name: str, handler: ListenerHandler) -> None:
        self._client.add_event_handler(event_name, handler)

    def remove_handler(self, event_name: str, handler: ListenerHandler) -> None:
        self._client.remove_event_handler(event_name, handler)

    def create_listener(self, event_name: str) -> VTSEventListener:
        listener = VTSEventListener(event_name=event_name, queue_size=self._queue_size)

        async def _queue_handler(event: VTSEventEnvelope) -> None:
            await listener.push(event)

        listener.handler = _queue_handler
        self._client.add_event_handler(event_name, _queue_handler)
        return listener

    def remove_listener(self, listener: VTSEventListener) -> None:
        handler = listener.handler
        if handler is not None:
            self._client.remove_event_handler(listener.event_name, handler)
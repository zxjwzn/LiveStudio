"""Async VTube Studio API client library."""

from .client import VTubeStudioClient
from .config import VTubeStudioConfig, VTubeStudioPluginInfo
from .discovery import VTubeStudioDiscovery
from .errors import (
    APIError,
    AuthenticationError,
    DiscoveryError,
    EventDispatchError,
    PermissionDeniedError,
    ResponseError,
    VTubeStudioConnectionError,
    VTubeStudioError,
)
from .event_listener import VTSEventListener
from .event_manager import ListenerHandler, VTSEventManager
from .examples import build_service
from .service import VTubeStudioService

__all__ = [
    "APIError",
    "AuthenticationError",
    "DiscoveryError",
    "EventDispatchError",
    "ListenerHandler",
    "PermissionDeniedError",
    "ResponseError",
    "VTSEventListener",
    "VTSEventManager",
    "VTubeStudioClient",
    "VTubeStudioConfig",
    "VTubeStudioConnectionError",
    "VTubeStudioDiscovery",
    "VTubeStudioError",
    "VTubeStudioPluginInfo",
    "VTubeStudioService",
    "build_service",
]

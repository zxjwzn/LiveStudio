"""用来异步连接 VTube Studio 的客户端"""

from .client import EventHandler as ListenerHandler
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

__all__ = [
    "APIError",
    "AuthenticationError",
    "DiscoveryError",
    "EventDispatchError",
    "ListenerHandler",
    "PermissionDeniedError",
    "ResponseError",
    "VTSEventListener",
    "VTubeStudioConfig",
    "VTubeStudioConnectionError",
    "VTubeStudioDiscovery",
    "VTubeStudioError",
    "VTubeStudioPluginInfo",
]

"""异步 VTube Studio API 客户端库。"""

from ...services.platforms.vtubestudio import VTubeStudio
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
    "VTubeStudio",
    "VTubeStudioConfig",
    "VTubeStudioConnectionError",
    "VTubeStudioDiscovery",
    "VTubeStudioError",
    "VTubeStudioPluginInfo",
]

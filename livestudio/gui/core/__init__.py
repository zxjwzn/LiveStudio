"""GUI 通用框架层。

与具体平台、具体页面无关的可复用基础设施：响应式原语、全局状态、
主题、跨线程桥接、视图基类、注册表与 view-model 定义。

依赖约束：本层仅允许依赖标准库与 flet，禁止 import bridge/ views/ 或后端。
"""

from __future__ import annotations

from .app_state import AppState
from .async_bridge import AsyncBridge
from .base_view import BaseView
from .choices_registry import ChoicesProvider, ChoicesRegistry
from .mount_aware import MountAware, SubscriptionHost, updates_ui
from .observable import Observable, ObservableList
from .registry import PlatformRegistry
from .theme import (
    PALETTE,
    TYPE,
    Palette,
    Typography,
    apply_page_theme,
    build_theme,
    connection_color,
    controller_color,
    level_color,
)
from .view_context import ViewContext
from .view_models import (
    AudioLevelVM,
    AudioSourceKind,
    ChoiceVM,
    ConfigFieldVM,
    ConfigSectionVM,
    ConnectionState,
    ControllerState,
    ControllerVM,
    DiscoveredEndpointVM,
    ExpressionVM,
    LogEntryVM,
    ModelConfigVM,
    PlatformDescriptor,
    PlatformStatusVM,
    audio_source_label,
    connection_label,
)

__all__ = [
    "PALETTE",
    "TYPE",
    "AppState",
    "AsyncBridge",
    "AudioLevelVM",
    "AudioSourceKind",
    "BaseView",
    "ChoiceVM",
    "ChoicesProvider",
    "ChoicesRegistry",
    "ConfigFieldVM",
    "ConfigSectionVM",
    "ConnectionState",
    "ControllerState",
    "ControllerVM",
    "DiscoveredEndpointVM",
    "ExpressionVM",
    "LogEntryVM",
    "ModelConfigVM",
    "Observable",
    "ObservableList",
    "Palette",
    "PlatformDescriptor",
    "PlatformRegistry",
    "PlatformStatusVM",
    "Typography",
    "ViewContext",
    "apply_page_theme",
    "audio_source_label",
    "build_theme",
    "connection_color",
    "connection_label",
    "controller_color",
    "level_color",
]

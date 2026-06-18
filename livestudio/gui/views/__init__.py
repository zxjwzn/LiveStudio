"""视图层：应用外壳与各页面。"""

from __future__ import annotations

from .audio import AudioView
from .dashboard import DashboardView
from .logs import LogsView
from .platform import PlatformView
from .settings import SettingsView
from .shell import AppShell

__all__ = [
    "AppShell",
    "AudioView",
    "DashboardView",
    "LogsView",
    "PlatformView",
    "SettingsView",
]

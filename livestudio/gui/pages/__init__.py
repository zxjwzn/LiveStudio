"""GUI 页面模块。"""

from .animations import AnimationsPage
from .audio import AudioPage
from .base import PageDefinition, PageViewBuilder
from .dashboard import DashboardPage
from .settings import SettingsPage
from .vtubestudio import VTubeStudioPage

__all__ = [
    "AnimationsPage",
    "AudioPage",
    "DashboardPage",
    "PageDefinition",
    "PageViewBuilder",
    "SettingsPage",
    "VTubeStudioPage",
]

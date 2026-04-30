"""GUI 通用组件。"""

from .cards import (
    MetricCard,
    StatusBadge,
    action_card,
    page_title,
)
from .controls import (
    icon_tile,
    primary_button,
    secondary_button,
    styled_dropdown,
    styled_progress_bar,
    styled_switch,
    styled_text_field,
    tonal_button,
)
from .header import HeaderBar
from .navigation import NavigationItem, SidebarNavigation
from .regions import placeholder_grid, placeholder_region

__all__ = [
    "HeaderBar",
    "MetricCard",
    "NavigationItem",
    "SidebarNavigation",
    "StatusBadge",
    "action_card",
    "icon_tile",
    "page_title",
    "placeholder_grid",
    "placeholder_region",
    "primary_button",
    "secondary_button",
    "styled_dropdown",
    "styled_progress_bar",
    "styled_switch",
    "styled_text_field",
    "tonal_button",
]

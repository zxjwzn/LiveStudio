"""页面定义协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import flet as ft


class PageViewBuilder(Protocol):
    """页面构建协议。"""

    route: str
    title: str
    description: str
    icon: str

    def build(self) -> ft.Control:
        """构建页面根控件。"""
        ...


@dataclass(frozen=True, slots=True)
class PageDefinition:
    """应用壳使用的页面定义。"""

    route: str
    title: str
    description: str
    icon: str
    view: PageViewBuilder

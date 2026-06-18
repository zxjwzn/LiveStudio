"""视图上下文：构造视图时注入的轻量依赖包。

避免每个视图都直接持有 ServiceBridge 全量引用；同时打破
views -> bridge 的强耦合（P0/P1 阶段 bridge 尚不存在，用 Any 占位）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .app_state import AppState


def _noop_navigate(_route: str) -> None:
    """默认路由跳转：空实现，由 AppShell 装配时替换。"""


@dataclass
class ViewContext:
    """注入视图的上下文。

    bridge 在 P2 接入 ServiceBridge 后填充；此前为 None。用 Any 标注以避免
    core 层反向依赖尚不存在的 bridge 包。
    """

    state: AppState
    bridge: Any = None
    navigate: Callable[[str], None] = field(default=_noop_navigate)

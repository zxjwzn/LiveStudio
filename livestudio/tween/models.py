"""缓动引擎使用的内部模型。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from .easing import EasingFunction


@dataclass(slots=True)
class ControlledParameterState:
    """由缓动引擎控制的参数运行时状态。"""

    name: str
    value: float
    mode: Literal["set", "add"]
    keep_alive: bool = True


@dataclass(slots=True)
class ActiveTween:
    """当前运行中的参数缓动任务元数据。"""

    task: asyncio.Task[None]
    priority: int
    mode: Literal["set", "add"]
    keep_alive: bool


@dataclass(slots=True)
class TweenRequest:
    """声明式缓动请求。"""

    parameter_name: str
    end_value: float
    duration: float
    easing: str | EasingFunction
    start_value: float | None = None
    delay: float = 0.0
    mode: Literal["set", "add"] = "set"
    fps: int = 60
    priority: int = 0
    keep_alive: bool = True

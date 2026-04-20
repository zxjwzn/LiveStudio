"""缓动引擎使用的内部模型。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from .easing import EasingFunction

TweenMode = Literal["set", "add"]


@dataclass(slots=True)
class ControlledParameterState:
    """由缓动引擎控制的参数运行时状态。"""

    name: str
    value: float
    mode: TweenMode
    keep_alive: bool = True


@dataclass(slots=True)
class ActiveTween:
    """当前运行中的参数缓动任务元数据。"""

    task: asyncio.Task[None]
    priority: int
    mode: TweenMode
    keep_alive: bool


@dataclass(slots=True)
class TweenRequest:
    """声明式缓动请求。"""

    parameter_name: str
    end_value: float
    duration: float
    easing_function: EasingFunction
    start_value: float | None = None
    mode: TweenMode = "set"
    fps: int = 60
    priority: int = 0
    keep_alive: bool = True

"""动画运行时的数据模型。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnimationType(StrEnum):
    """动画控制器类型。"""

    IDLE = "idle"
    ONESHOT = "oneshot"

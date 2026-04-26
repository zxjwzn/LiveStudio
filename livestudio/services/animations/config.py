from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .controllers.blink.config import BlinkControllerConfig
from .controllers.breath.config import BreathingControllerConfig


class ControllerSettings(BaseModel):
    """控制器配置基类。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="是否启用控制器。")


class ModelAnimationConfig(BaseModel):
    """绑定到单个模型的动画控制器配置。"""

    model_config = ConfigDict(extra="forbid")

    blink: BlinkControllerConfig = Field(
        default_factory=BlinkControllerConfig,
        description="眨眼控制器配置。",
    )
    breathing: BreathingControllerConfig = Field(
        default_factory=BreathingControllerConfig,
        description="呼吸控制器配置。",
    )

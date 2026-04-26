from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...config import ControllerSettings


class BlinkControllerConfig(ControllerSettings):
    """眨眼控制器配置。"""

    left_parameter: str = Field(default="EyeOpenLeft", description="左眼参数名。")
    right_parameter: str = Field(default="EyeOpenRight", description="右眼参数名。")
    open_value: float = Field(default=1.0, description="睁眼值。")
    closed_value: float = Field(default=0.0, description="闭眼值。")
    min_interval: float = Field(default=2.0, gt=0, description="最小间隔秒数。")
    max_interval: float = Field(default=4.0, gt=0, description="最大间隔秒数。")
    close_duration: float = Field(default=0.15, ge=0, description="闭眼耗时。")
    hold_duration: float = Field(default=0.05, ge=0, description="闭眼保持耗时。")
    open_duration: float = Field(default=0.3, ge=0, description="睁眼耗时。")
    easing: str = Field(default="in_out_sine", description="眨眼缓动函数。")

    @model_validator(mode="after")
    def validate_interval_range(self) -> BlinkControllerConfig:
        if self.max_interval < self.min_interval:
            raise ValueError("max_interval 不能小于 min_interval")
        return self

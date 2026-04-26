from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...config import ControllerSettings


class BreathingControllerConfig(ControllerSettings):
    """呼吸控制器配置。"""

    parameter: str = Field(default="FaceAngleY", description="呼吸驱动参数。")
    min_value: float = Field(default=-3.0, description="呼气阶段参数值。")
    max_value: float = Field(default=3.0, description="吸气阶段参数值。")
    inhale_duration: float = Field(default=1.0, gt=0, description="吸气时长。")
    exhale_duration: float = Field(default=2.0, gt=0, description="呼气时长。")
    easing: str = Field(default="in_out_sine", description="单段缓动函数。")

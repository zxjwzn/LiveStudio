from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ControllerSettings(BaseModel):
    """控制器配置基类。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="是否启用控制器。")

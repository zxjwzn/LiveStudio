"""平台服务运行时模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PlatformModelIdentity(BaseModel):
    """平台当前加载模型的运行时身份。"""

    model_config = ConfigDict(extra="forbid")

    platform_name: str = Field(description="平台唯一名称。")
    model_id: str = Field(description="平台模型唯一 ID。")
    model_name: str = Field(description="平台模型显示名称。")

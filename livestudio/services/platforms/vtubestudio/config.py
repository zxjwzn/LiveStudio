"""VTube Studio 平台服务配置模型。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from livestudio.services.animations.controllers import (
    BlinkControllerSettings,
    BodySwingControllerSettings,
    BreathingControllerSettings,
    MouthExpressionControllerSettings,
    MouthSyncControllerSettings,
)


class VTubeStudioModelInfoConfig(BaseModel):
    """写入模型配置文件的 VTube Studio 模型标识。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default="", description="VTube Studio 模型唯一 ID。")
    name: str = Field(default="", description="VTube Studio 模型显示名称。")


class VTubeStudioPlatformModelSettings(BaseModel):
    """随模型切换的 VTube Studio 平台层配置。"""

    model_config = ConfigDict(extra="forbid")

    parameter_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="平台参数名映射覆盖表。",
    )


class VTubeStudioExpressionStateConfig(BaseModel):
    """VTube Studio 表情激活状态配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", description="表情名称。")
    file: str = Field(default="", description="表情文件名。")
    active: bool = Field(default=False, description="模型加载时是否激活该表情。")


class VTubeStudioControllerSettingsConfig(BaseModel):
    """随模型切换的 VTube Studio 动画控制器配置。"""

    model_config = ConfigDict(extra="forbid")

    blink: BlinkControllerSettings = Field(
        default_factory=BlinkControllerSettings,
        description="眨眼控制器配置。",
    )
    breathing: BreathingControllerSettings = Field(
        default_factory=BreathingControllerSettings,
        description="呼吸控制器配置。",
    )
    body_swing: BodySwingControllerSettings = Field(
        default_factory=BodySwingControllerSettings,
        description="身体摇摆控制器配置。",
    )
    mouth_expression: MouthExpressionControllerSettings = Field(
        default_factory=MouthExpressionControllerSettings,
        description="嘴部表情控制器配置。",
    )
    mouth_sync: MouthSyncControllerSettings = Field(
        default_factory=MouthSyncControllerSettings,
        description="基于响度的嘴部开合同步控制器配置。",
    )


class VTubeStudioModelConfig(BaseModel):
    """按 VTube Studio 模型持久化的完整平台配置。"""

    model_config = ConfigDict(extra="forbid")

    model: VTubeStudioModelInfoConfig = Field(
        default_factory=VTubeStudioModelInfoConfig,
        description="当前配置绑定的 VTube Studio 模型。",
    )
    platform: VTubeStudioPlatformModelSettings = Field(
        default_factory=VTubeStudioPlatformModelSettings,
        description="平台层随模型切换的配置。",
    )
    controllers: VTubeStudioControllerSettingsConfig = Field(
        default_factory=VTubeStudioControllerSettingsConfig,
        description="动画控制器配置。",
    )
    expressions: list[VTubeStudioExpressionStateConfig] = Field(
        default_factory=list,
        description="模型加载时需要同步的表情激活状态配置。",
    )

    @field_validator("expressions", mode="before")
    @classmethod
    def migrate_expression_mapping(cls, value: Any) -> Any:
        """兼容旧版按文件名索引的表情配置。"""

        if isinstance(value, dict):
            return list(value.values())
        return value

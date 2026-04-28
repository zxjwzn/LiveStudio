"""VTube Studio 平台服务配置模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.animations.controllers import (
    BlinkControllerSettings,
    BodySwingControllerSettings,
    BreathingControllerSettings,
    MouthExpressionControllerSettings,
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

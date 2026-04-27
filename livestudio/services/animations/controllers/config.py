from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ControllerSettings(BaseModel):
    """控制器配置基类。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="是否启用控制器。")


class BlinkControllerSettings(ControllerSettings):
    """眨眼控制器配置。"""

    min_interval: float = Field(
        default=2.0,
        gt=0,
        description="两次眨眼之间的最小间隔时间。",
    )
    max_interval: float = Field(
        default=4.0,
        gt=0,
        description="两次眨眼之间的最大间隔时间。",
    )
    close_duration: float = Field(default=0.15, ge=0, description="闭眼动画持续时间。")
    open_duration: float = Field(default=0.3, ge=0, description="睁眼动画持续时间。")
    closed_hold: float = Field(default=0.05, ge=0, description="眼睛闭合状态保持时间。")


class BreathingControllerSettings(ControllerSettings):
    """呼吸控制器配置。"""

    min_value: float = Field(default=-3.0, description="呼吸参数最小值。")
    max_value: float = Field(default=3.0, description="呼吸参数最大值。")
    inhale_duration: float = Field(default=1.0, ge=0, description="吸气持续时间。")
    exhale_duration: float = Field(default=2.0, ge=0, description="呼气持续时间。")


class EyeFollowControllerSettings(ControllerSettings):
    """身体摇摆时的眼睛跟随配置。"""

    x_min_range: float = Field(default=-1.0, description="眼睛水平移动最小值。")
    x_max_range: float = Field(default=1.0, description="眼睛水平移动最大值。")
    y_min_range: float = Field(default=-1.0, description="眼睛垂直移动最小值。")
    y_max_range: float = Field(default=1.0, description="眼睛垂直移动最大值。")


class BodySwingControllerSettings(ControllerSettings):
    """身体摇摆控制器配置。"""

    x_min: float = Field(default=-10.0, description="身体左右摇摆最小位置。")
    x_max: float = Field(default=15.0, description="身体左右摇摆最大位置。")
    z_min: float = Field(default=-10.0, description="上肢旋转最小位置。")
    z_max: float = Field(default=15.0, description="上肢旋转最大位置。")
    min_duration: float = Field(default=2.0, ge=0, description="摇摆最短持续时间。")
    max_duration: float = Field(default=8.0, ge=0, description="摇摆最长持续时间。")
    eye_follow: EyeFollowControllerSettings = Field(
        default_factory=EyeFollowControllerSettings,
        description="眼睛跟随配置。",
    )

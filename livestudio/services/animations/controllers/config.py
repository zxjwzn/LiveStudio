from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class MouthExpressionControllerSettings(ControllerSettings):
    """嘴部表情控制器配置。"""

    smile_min: float = Field(default=-0.2, description="微笑参数随机最小值。")
    smile_max: float = Field(default=0.8, description="微笑参数随机最大值。")
    open_min: float = Field(default=0.0, description="嘴巴张开参数随机最小值。")
    open_max: float = Field(default=0.3, description="嘴巴张开参数随机最大值。")
    min_duration: float = Field(default=1.0, ge=0, description="变化最短持续时间。")
    max_duration: float = Field(default=4.0, ge=0, description="变化最长持续时间。")


class MouthSyncParameterMapping(BaseModel):
    """嘴型姿态到 VTube Studio 参数的映射。"""

    model_config = ConfigDict(extra="forbid")

    open: str = Field(default="MouthOpen", min_length=1, description="嘴部开合参数。")
    smile: str | None = Field(default="MouthSmile", description="嘴部形状参数。")
    x: str | None = Field(default="MouthX", description="嘴部横向动态参数。")


class MouthPoseConfig(BaseModel):
    """嘴型目标姿态配置。"""

    model_config = ConfigDict(extra="forbid")

    open: float = Field(default=0.0, ge=0.0, le=1.0, description="嘴部开合值。")
    smile: float = Field(default=0.5, ge=0.0, le=1.0, description="嘴部形状值。")
    x: float = Field(default=0.0, ge=-1.0, le=1.0, description="嘴部横向偏移值。")


class MouthSyncControllerSettings(ControllerSettings):
    """嘴型同步控制器配置。"""

    mode: Literal["loudness", "spectral"] = Field(
        default="spectral",
        description="嘴型同步算法模式。",
    )
    parameters: MouthSyncParameterMapping = Field(
        default_factory=MouthSyncParameterMapping,
        description="嘴型姿态参数映射。",
    )
    closed_pose: MouthPoseConfig = Field(
        default_factory=MouthPoseConfig,
        description="静音或停止时的嘴型姿态。",
    )
    open_min: float = Field(default=0.1, description="说话时的最小开口值。")
    open_max: float = Field(default=0.85, description="最大开口值。")
    noise_floor: float = Field(default=0.01, ge=0.0, description="静音门限。")
    voice_ceiling: float = Field(default=0.2, gt=0.0, description="有效语音上限。")
    neutral_smile: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="自然嘴角基准值。",
    )
    min_smile: float = Field(default=0.05, ge=0.0, le=1.0, description="最小嘴型值。")
    max_smile: float = Field(default=0.95, ge=0.0, le=1.0, description="最大嘴型值。")
    smile_open_compensation: float = Field(
        default=0.16,
        ge=0.0,
        description="嘴角上扬造成视觉开口放大时的开合补偿。",
    )
    low_smile_open_boost: float = Field(
        default=0.06,
        ge=0.0,
        description="嘴角下压时的开合补偿。",
    )
    high_band_smile_gain: float = Field(
        default=0.55,
        ge=0.0,
        description="高频能量对嘴角上扬的增益。",
    )
    low_band_smile_gain: float = Field(
        default=0.45,
        ge=0.0,
        description="低频能量对圆唇/下压嘴型的增益。",
    )
    x_enabled: bool = Field(default=True, description="是否启用 MouthX 轻微动态。")
    x_max_offset: float = Field(
        default=0.06,
        ge=0.0,
        le=1.0,
        description="MouthX 动态最大绝对值。",
    )
    x_activity_gain: float = Field(
        default=0.08,
        ge=0.0,
        description="音量变化对 MouthX 动态的增益。",
    )
    open_smoothing: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="嘴部开合平滑系数。",
    )
    smile_smoothing: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="嘴部形状平滑系数。",
    )
    x_smoothing: float = Field(
        default=0.18,
        ge=0.0,
        le=1.0,
        description="嘴部横向动态平滑系数。",
    )
    update_interval: float = Field(default=0.02, gt=0.0, description="更新间隔。")
    attack_duration: float = Field(default=0.02, ge=0.0, description="张嘴过渡时长。")
    release_duration: float = Field(default=0.04, ge=0.0, description="闭嘴过渡时长。")
    priority: int = Field(default=20, description="嘴型参数控制优先级。")

    @model_validator(mode="after")
    def validate_mouth_sync_range(self) -> MouthSyncControllerSettings:
        if self.open_max < self.open_min:
            raise ValueError("open_max 不能小于 open_min")
        if self.voice_ceiling <= self.noise_floor:
            raise ValueError("voice_ceiling 必须大于 noise_floor")
        if self.max_smile < self.min_smile:
            raise ValueError("max_smile 不能小于 min_smile")
        return self

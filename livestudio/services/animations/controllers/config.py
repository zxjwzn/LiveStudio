from __future__ import annotations

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

    min_value: float = Field(
        default=-3.0,
        ge=-30.0,
        le=30.0,
        description="呼吸参数最小值。",
    )
    max_value: float = Field(
        default=3.0,
        ge=-30.0,
        le=30.0,
        description="呼吸参数最大值。",
    )
    inhale_duration: float = Field(default=1.0, ge=0, description="吸气持续时间。")
    exhale_duration: float = Field(default=2.0, ge=0, description="呼气持续时间。")

    @model_validator(mode="after")
    def validate_breathing_range(self) -> BreathingControllerSettings:
        if self.max_value < self.min_value:
            raise ValueError("max_value 不能小于 min_value")
        return self


class BodySwingControllerSettings(ControllerSettings):
    """身体摇摆控制器配置。"""

    x_min: float = Field(
        default=-10.0,
        ge=-30.0,
        le=30.0,
        description="身体左右摇摆最小位置。",
    )
    x_max: float = Field(
        default=15.0,
        ge=-30.0,
        le=30.0,
        description="身体左右摇摆最大位置。",
    )
    z_min: float = Field(
        default=-10.0,
        ge=-90.0,
        le=90.0,
        description="上肢旋转最小位置。",
    )
    z_max: float = Field(
        default=15.0,
        ge=-90.0,
        le=90.0,
        description="上肢旋转最大位置。",
    )
    min_duration: float = Field(default=2.0, ge=0, description="摇摆最短持续时间。")
    max_duration: float = Field(default=8.0, ge=0, description="摇摆最长持续时间。")

    @model_validator(mode="after")
    def validate_body_swing_range(self) -> BodySwingControllerSettings:
        if self.x_max < self.x_min:
            raise ValueError("x_max 不能小于 x_min")
        if self.z_max < self.z_min:
            raise ValueError("z_max 不能小于 z_min")
        return self


class MouthExpressionControllerSettings(ControllerSettings):
    """嘴部表情控制器配置。"""

    smile_min: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="微笑参数随机最小值。",
    )
    smile_max: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="微笑参数随机最大值。",
    )
    open_min: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="嘴巴张开参数随机最小值。",
    )
    open_max: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="嘴巴张开参数随机最大值。",
    )
    min_duration: float = Field(default=1.0, ge=0, description="变化最短持续时间。")
    max_duration: float = Field(default=4.0, ge=0, description="变化最长持续时间。")

    @model_validator(mode="after")
    def validate_mouth_expression_range(self) -> MouthExpressionControllerSettings:
        if self.smile_max < self.smile_min:
            raise ValueError("smile_max 不能小于 smile_min")
        if self.open_max < self.open_min:
            raise ValueError("open_max 不能小于 open_min")
        return self


class MouthSyncControllerSettings(ControllerSettings):
    """基于响度的嘴部开合同步控制器配置。"""

    open_min: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="说话时的最小开口值。",
    )
    open_max: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="说话时的最大开口值。",
    )
    noise_floor: float = Field(default=0.01, ge=0.0, description="静音门限。")
    voice_ceiling: float = Field(default=0.2, gt=0.0, description="有效语音上限。")
    open_smoothing: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="嘴部开合平滑系数。",
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
        return self

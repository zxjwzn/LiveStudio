from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ControllerSettings(BaseModel):
    """控制器配置基类"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="是否启用控制器")


class BlinkControllerSettings(ControllerSettings):
    """眨眼控制器配置"""

    min_interval: float = Field(
        default=2.0,
        gt=0,
        description="两次眨眼之间的最小间隔时间",
    )
    max_interval: float = Field(
        default=4.0,
        gt=0,
        description="两次眨眼之间的最大间隔时间",
    )
    close_duration: float = Field(default=0.15, ge=0, description="闭眼动画持续时间")
    open_duration: float = Field(default=0.3, ge=0, description="睁眼动画持续时间")
    closed_hold: float = Field(default=0.05, ge=0, description="眼睛闭合状态保持时间")


class BreathingControllerSettings(ControllerSettings):
    """呼吸控制器配置"""

    pitch_amplitude: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="呼吸带来的头部俯仰语义强度",
    )
    inhale_duration: float = Field(default=1.0, ge=0, description="吸气持续时间")
    exhale_duration: float = Field(default=2.0, ge=0, description="呼气持续时间")


class BodySwingControllerSettings(ControllerSettings):
    """身体摇摆控制器配置"""

    yaw_amplitude: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="头部左右偏转强度",
    )
    roll_amplitude: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="头部侧倾强度",
    )
    min_duration: float = Field(default=2.0, ge=0, description="摇摆最短持续时间")
    max_duration: float = Field(default=8.0, ge=0, description="摇摆最长持续时间")

    @model_validator(mode="after")
    def validate_body_swing_range(self) -> BodySwingControllerSettings:
        if self.max_duration < self.min_duration:
            raise ValueError("max_duration 不能小于 min_duration")
        return self


class EyeCenteringControllerSettings(ControllerSettings):
    """基于头部姿态的眼球居中补偿控制器配置"""

    yaw_compensation: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="头部左右偏转对眼球 X 轴的反向补偿强度",
    )
    pitch_compensation: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        description="头部俯仰对眼球 Y 轴的反向补偿强度",
    )
    roll_to_x_compensation: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="头部侧倾对眼球 X 轴的补偿强度",
    )
    roll_to_y_compensation: float = Field(
        default=0.0,
        ge=-2.0,
        le=2.0,
        description="头部侧倾对眼球 Y 轴的补偿强度",
    )
    update_interval: float = Field(default=0.05, gt=0.0, description="更新间隔")
    duration: float = Field(default=0.05, ge=0.0, description="补偿缓动时长")
    smoothing: float = Field(default=0.35, ge=0.0, le=1.0, description="补偿平滑系数")
    deadzone: float = Field(default=0.01, ge=0.0, le=1.0, description="小幅变化死区")
    priority: int = Field(default=15, description="眼球居中参数控制优先级")


class MouthExpressionControllerSettings(ControllerSettings):
    """嘴部表情控制器配置"""

    smile_amplitude: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="微笑强度",
    )
    min_duration: float = Field(default=1.0, ge=0, description="变化最短持续时间")
    max_duration: float = Field(default=4.0, ge=0, description="变化最长持续时间")

    @model_validator(mode="after")
    def validate_mouth_expression_range(self) -> MouthExpressionControllerSettings:
        if self.max_duration < self.min_duration:
            raise ValueError("max_duration 不能小于 min_duration")
        return self


class MouthSyncControllerSettings(ControllerSettings):
    """基于响度的嘴部开合同步控制器配置"""

    open_amplitude: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="语音响度映射到嘴部张开的强度",
    )
    noise_floor: float = Field(default=0.01, ge=0.0, description="静音门限")
    voice_ceiling: float = Field(default=0.2, gt=0.0, description="有效语音上限")
    open_smoothing: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="嘴部开合平滑系数",
    )
    update_interval: float = Field(default=0.02, gt=0.0, description="更新间隔")
    attack_duration: float = Field(default=0.02, ge=0.0, description="张嘴过渡时长")
    release_duration: float = Field(default=0.04, ge=0.0, description="闭嘴过渡时长")
    priority: int = Field(default=20, description="嘴型参数控制优先级")

    @model_validator(mode="after")
    def validate_mouth_sync_range(self) -> MouthSyncControllerSettings:
        if self.voice_ceiling <= self.noise_floor:
            raise ValueError("voice_ceiling 必须大于 noise_floor")
        return self

class AnimationControllerSettingsConfig(BaseModel):
    """随模型切换的全平台通用动画控制器配置"""

    model_config = ConfigDict(extra="forbid")

    blink: BlinkControllerSettings = Field(
        default_factory=BlinkControllerSettings,
        description="眨眼控制器配置",
    )
    breathing: BreathingControllerSettings = Field(
        default_factory=BreathingControllerSettings,
        description="呼吸控制器配置",
    )
    body_swing: BodySwingControllerSettings = Field(
        default_factory=BodySwingControllerSettings,
        description="身体摇摆控制器配置",
    )
    eye_centering: EyeCenteringControllerSettings = Field(
        default_factory=EyeCenteringControllerSettings,
        description="眼球居中补偿控制器配置",
    )
    mouth_expression: MouthExpressionControllerSettings = Field(
        default_factory=MouthExpressionControllerSettings,
        description="嘴部表情控制器配置",
    )
    mouth_sync: MouthSyncControllerSettings = Field(
        default_factory=MouthSyncControllerSettings,
        description="基于响度的嘴部开合同步控制器配置",
    )


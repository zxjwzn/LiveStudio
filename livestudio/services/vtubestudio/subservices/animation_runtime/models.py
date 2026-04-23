"""动画运行时的数据模型。"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from livestudio.tween import TweenMode

from ..base import SubserviceConfigFile

TemplateScalar = float | int | bool | str
TemplateValue = TemplateScalar | dict[str, Any]
CONTROLLER_PRIORITY = 10
TEMPLATE_PRIORITY = 20


class AnimationType(StrEnum):
    """动画控制器类型。"""

    IDLE = "idle"
    ONESHOT = "oneshot"


class ControllerSettings(BaseModel):
    """控制器配置基类。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="是否启用控制器。")


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


class BreathingControllerConfig(ControllerSettings):
    """呼吸控制器配置。"""

    parameter: str = Field(default="FaceAngleY", description="呼吸驱动参数。")
    min_value: float = Field(default=-3.0, description="呼气阶段参数值。")
    max_value: float = Field(default=3.0, description="吸气阶段参数值。")
    inhale_duration: float = Field(default=1.0, gt=0, description="吸气时长。")
    exhale_duration: float = Field(default=2.0, gt=0, description="呼气时长。")
    easing: str = Field(default="in_out_sine", description="单段缓动函数。")


class MouthSyncControllerConfig(ControllerSettings):
    """嘴型同步控制器配置。"""

    parameter: str = Field(default="MouthOpen", description="嘴型开合参数名。")
    closed_value: float = Field(default=0.0, description="闭嘴值。")
    open_min: float = Field(default=0.1, description="说话时的最小开口值。")
    open_max: float = Field(default=1.0, description="最大开口值。")
    noise_floor: float = Field(default=0.01, ge=0.0, description="静音门限。")
    voice_ceiling: float = Field(default=0.2, gt=0.0, description="有效语音上限。")
    smoothing_factor: float = Field(default=0.35, ge=0.0, le=1.0, description="嘴型平滑系数。")
    update_interval: float = Field(default=0.05, gt=0.0, description="更新间隔。")
    attack_duration: float = Field(default=0.04, ge=0.0, description="张嘴过渡时长。")
    release_duration: float = Field(default=0.08, ge=0.0, description="闭嘴过渡时长。")
    priority: int = Field(default=30, description="嘴型参数控制优先级。")

    @model_validator(mode="after")
    def validate_mouth_sync_range(self) -> MouthSyncControllerConfig:
        if self.open_max < self.open_min:
            raise ValueError("open_max 不能小于 open_min")
        if self.voice_ceiling <= self.noise_floor:
            raise ValueError("voice_ceiling 必须大于 noise_floor")
        return self


class TemplateParameterDefinition(BaseModel):
    """模板可接收的外部参数声明。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="参数名。")
    description: str | None = Field(default=None, description="参数说明。")
    type: str | None = Field(default=None, description="参数类型声明。")
    default: TemplateScalar | None = Field(default=None, description="默认值。")
    required: bool = Field(default=False, description="是否必须传入。")


class TemplateActionDefinition(BaseModel):
    """模板中的单个参数动作。"""

    model_config = ConfigDict(extra="forbid")

    parameter: str = Field(min_length=1, description="目标参数名。")
    to: TemplateValue = Field(description="目标值。")
    duration: TemplateValue = Field(default=0.0, description="动作时长。")
    from_value: TemplateValue | None = Field(default=None, alias="from", description="可选起始值。")
    delay: TemplateValue = Field(default=0.0, description="动作延迟。")
    easing: str = Field(default="linear", description="缓动函数名。")
    mode: TweenMode = Field(default="set", description="参数写入模式。")


class TemplateDataDefinition(BaseModel):
    """模板主体。"""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, description="模板说明。")
    params: list[TemplateParameterDefinition] = Field(default_factory=list, description="外部参数声明。")
    variables: dict[str, TemplateValue] = Field(default_factory=dict, description="内部变量定义。")
    actions: list[TemplateActionDefinition] = Field(default_factory=list, description="动作列表。")


class AnimationTemplate(BaseModel):
    """动画模板文件结构。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="模板名称。")
    type: Literal["animation"] = Field(default="animation", description="模板类型。")
    data: TemplateDataDefinition = Field(default_factory=TemplateDataDefinition, description="模板主体数据。")


class AnimationRuntimeConfig(BaseModel):
    """动画运行时配置。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="运行时内部逻辑开关。")
    template_dir: str = Field(default="config/animations", description="动画模板目录。")
    auto_start_idle: bool = Field(default=True, description="启动子服务时是否自动启动循环控制器。")
    tick_fps: int = Field(default=60, ge=1, le=240, description="逻辑采样频率提示值。")
    blink: BlinkControllerConfig = Field(default_factory=BlinkControllerConfig, description="眨眼控制器配置。")
    breathing: BreathingControllerConfig = Field(default_factory=BreathingControllerConfig, description="呼吸控制器配置。")
    mouth_sync: MouthSyncControllerConfig = Field(default_factory=MouthSyncControllerConfig, description="嘴型同步控制器配置。")

    def resolve_template_dir(self) -> Path:
        return Path(self.template_dir)


class AnimationRuntimeConfigFile(SubserviceConfigFile[AnimationRuntimeConfig]):
    """动画运行时子服务配置文件。"""

    config: AnimationRuntimeConfig = Field(default_factory=AnimationRuntimeConfig)


class ResolvedTemplateAction(BaseModel):
    """模板动作求值后的结果。"""

    model_config = ConfigDict(extra="forbid")

    parameter: str
    to: float
    duration: float
    from_value: float | None = None
    delay: float = 0.0
    easing: str = "linear"
    mode: TweenMode = "set"
    priority: int = TEMPLATE_PRIORITY
    keep_alive: bool = True


class TemplatePlayback(BaseModel):
    """一次模板播放的完整求值结果。"""

    model_config = ConfigDict(extra="forbid")

    template_name: str
    context: dict[str, TemplateScalar] = Field(default_factory=dict)
    actions: list[ResolvedTemplateAction] = Field(default_factory=list)

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from livestudio.services.audio_stream.sources.tts.engines.fish_audio import FishAudioSpeakConfig
from livestudio.services.audio_stream.sources.tts.engines.types import TtsProviderKind, TtsSpeakRequest


class ControllerSettings(BaseModel):
    """控制器配置基类。

    控制器是否运行由运行态启停(仪表盘开关 / MCP set_controller)决定,不再有
    配置级 ``enabled`` 开关;各控制器优先级亦固化为代码常量,不进配置。
    """

    model_config = ConfigDict(extra="forbid")


class BlinkControllerSettings(ControllerSettings):
    """眨眼控制器配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "VIEW"})

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

    @model_validator(mode="after")
    def validate_blink_range(self) -> "BlinkControllerSettings":
        if self.max_interval < self.min_interval:
            raise ValueError("max_interval 不能小于 min_interval")
        return self


class BreathingControllerSettings(ControllerSettings):
    """呼吸控制器配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "LEAF"})

    pitch_amplitude: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="呼吸带来的头部俯仰语义强度",
    )
    inhale_duration: float = Field(default=1.0, ge=0, description="吸气持续时间")
    exhale_duration: float = Field(default=2.0, ge=0, description="呼气持续时间")


class GazeControllerSettings(ControllerSettings):
    """眼神注视控制器配置。

    统一驱动 eye.gaze.x/y 与 head.yaw/head.pitch/head.roll:眼睛以中心高频轻微扰动为主,
    偶尔随机注视到一处,头部可跟随、不跟随或反向移动。

    仅暴露 5 个用户可调旋钮;各时长/概率/微扰幅度/均衡窗口等已固化为 gaze 模块常量,
    行为不变但禁止用户调整。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SEARCH"})

    gaze_x_amplitude: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="眼睛左右注视幅度（语义值域 -1~1，越大眼神越能转到边缘）",
    )
    gaze_y_amplitude: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="眼睛上下注视幅度（上下幅度通常略小于左右，避免翻白眼）",
    )
    head_follow_strength: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="头部跟随眼神的整体强度（0=头不动，1=默认）；统一缩放头部 yaw/pitch/roll 三轴跟随",
    )
    head_follow_chance: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="本次眼动是否带动头部转动的基础概率；大幅度注视会在此基础上提高转头倾向，"
        "未命中时只动眼睛、头保持回正，模拟真人小幅扫视纯眼动、大角度才扭头",
    )
    reverse_head_chance: float = Field(
        default=0.18,
        ge=0.0,
        le=1.0,
        description="头部反向跟随的概率：看一侧、头却朝另一侧偏/歪，制造俏皮歪头",
    )


class MouthExpressionControllerSettings(ControllerSettings):
    """嘴部表情控制器配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "EMOJI_TAB_SYMBOLS"})

    smile_amplitude: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="微笑强度",
    )
    min_duration: float = Field(default=1.0, ge=0, description="变化最短持续时间")
    max_duration: float = Field(default=4.0, ge=0, description="变化最长持续时间")

    @model_validator(mode="after")
    def validate_mouth_expression_range(self) -> "MouthExpressionControllerSettings":
        if self.max_duration < self.min_duration:
            raise ValueError("max_duration 不能小于 min_duration")
        return self


class MouthSyncControllerSettings(ControllerSettings):
    """基于响度的嘴部开合同步控制器配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "MICROPHONE"})

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
    update_interval: float = Field(default=0.0167, gt=0.0, description="更新间隔")
    attack_duration: float = Field(default=0.02, ge=0.0, description="张嘴过渡时长")
    release_duration: float = Field(default=0.04, ge=0.0, description="闭嘴过渡时长")

    @model_validator(mode="after")
    def validate_mouth_sync_range(self) -> "MouthSyncControllerSettings":
        if self.voice_ceiling <= self.noise_floor:
            raise ValueError("voice_ceiling 必须大于 noise_floor")
        return self


class ExpressionControllerSettings(ControllerSettings):
    """表情解算控制器配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "HEART"})

    transition_duration: float = Field(
        default=0.5,
        ge=0.0,
        description="解算后从当前值切换到目标表情的过渡时长",
    )
    hold_duration: float = Field(
        default=1,
        ge=0.0,
        description="到达目标后保持时长，期间高优先级占用参数，<=0 时跳过保持段",
    )
    history_capacity: int = Field(
        default=5,
        ge=0,
        description="解算历史保留条数，用于重复惩罚",
    )
    top_candidates: int = Field(
        default=20,
        ge=1,
        description="评分后保留进入排序阶段的候选数量上限",
    )
    typicality_floor: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="典型度硬门 τ：AU 在当前情绪的分低于其本职峰值该比例时直接剔除；0=关闭（退化旧行为）",
    )
    typicality_power: float = Field(
        default=0.5,
        ge=0.0,
        description="典型度软折扣指数 α：客串 AU 入选概率乘 typicality^α；0=关闭折扣，越大越偏爱本职 AU",
    )
    neutral_transition_duration: float = Field(
        default=0.5,
        ge=0.0,
        description="保持结束后回归静息的过渡时长",
    )



class TTSpeakControllerSettings(ControllerSettings):
    """TTS 发声 oneshot:kind 选中激活供应商,各供应商 speak 配置并列(未用也留配置)。

    合成/字幕文本运行时经 ``TTSpeakRequest`` 传入。
    全局连接与 model/latency/speed 在 audio_stream.tts.<供应商>;
    本配置仅保留 per-model 音色与字幕推送速率。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SPEAKERS"})

    kind: TtsProviderKind = Field(
        default="fish_audio",
        description="激活的 TTS 供应商(决定取哪个 speak 配置与全局连接槽)",
    )
    fish_audio: FishAudioSpeakConfig = Field(
        default_factory=FishAudioSpeakConfig,
        description="Fish Audio 发声参数(仅 reference_id/音色)",
    )
    subtitle_chars_per_second: float = Field(
        default=8.0,
        gt=0.0,
        le=60.0,
        description="字幕逐字推送速率(字/秒);仅影响字幕总线,不改变 TTS 音频",
    )

    def as_speak_request(self) -> TtsSpeakRequest:
        """构造引擎侧 ``TtsSpeakRequest``(kind + 激活供应商发声参数)。"""

        if self.kind == "fish_audio":
            return TtsSpeakRequest(kind=self.kind, fish_audio=self.fish_audio)
        return TtsSpeakRequest(kind=self.kind)


class AnimationControllerSettingsConfig(BaseModel):
    """随模型切换的全平台通用动画控制器配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "MOVIE"})

    blink: BlinkControllerSettings = Field(
        default_factory=BlinkControllerSettings,
        description="眨眼控制器配置",
    )
    breathing: BreathingControllerSettings = Field(
        default_factory=BreathingControllerSettings,
        description="呼吸控制器配置",
    )
    gaze: GazeControllerSettings = Field(
        default_factory=GazeControllerSettings,
        description="眼神注视控制器配置",
    )
    mouth_expression: MouthExpressionControllerSettings = Field(
        default_factory=MouthExpressionControllerSettings,
        description="嘴部表情控制器配置",
    )
    mouth_sync: MouthSyncControllerSettings = Field(
        default_factory=MouthSyncControllerSettings,
        description="基于响度的嘴部开合同步控制器配置",
    )
    expression: ExpressionControllerSettings = Field(
        default_factory=ExpressionControllerSettings,
        description="表情解算控制器配置",
    )
    tts_speak: TTSpeakControllerSettings = Field(
        default_factory=TTSpeakControllerSettings,
        description="TTS 发声 oneshot(引擎/音色随模型;文本运行时传入)",
    )

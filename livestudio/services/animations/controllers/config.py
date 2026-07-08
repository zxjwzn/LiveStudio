from pydantic import BaseModel, ConfigDict, Field, model_validator


class ControllerSettings(BaseModel):
    """控制器配置基类"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="是否启用控制器")


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
    """眼神注视控制器配置

    统一驱动 eye.gaze.x/y 与 head.yaw/head.pitch/head.roll：眼睛以中心高频轻微扰动为主，
    偶尔随机注视到一处，头部可跟随、不跟随或反向移动。
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
    head_follow_ratio: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="头部偏转跟随眼神方向的比例（head_yaw = gaze_x * ratio），越大眼神转动时头跟得越多",
    )
    head_follow_chance: float = Field(
        default=0.55,
        ge=0.0,
        le=1.0,
        description="本次眼动是否带动头部转动的基础概率；大幅度注视会在此基础上提高转头倾向，"
        "未命中时只动眼睛、头保持回正，模拟真人小幅扫视纯眼动、大角度才扭头",
    )
    head_roll_ratio: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="头部侧倾跟随眼神方向的比例（head_roll = gaze_x * ratio）",
    )
    head_pitch_ratio: float = Field(
        default=0.18,
        ge=0.0,
        le=1.0,
        description="头部俯仰跟随眼神上下方向的比例（head_pitch = gaze_y * ratio）",
    )
    head_follow_delay: float = Field(
        default=0.12,
        ge=0.0,
        description="头部跟随相对眼睛扫视的启动延迟，模拟前庭眼反射",
    )
    head_follow_duration: float = Field(
        default=0.8,
        gt=0.0,
        description="头部跟随到位的过渡时长（比眼睛扫视慢）",
    )
    min_saccade_duration: float = Field(
        default=0.08,
        gt=0.0,
        description="眼睛扫视到位的最短时长",
    )
    max_saccade_duration: float = Field(
        default=0.22,
        gt=0.0,
        description="眼睛扫视到位的最长时长",
    )
    reach_min_scale: float = Field(
        default=0.4,
        gt=0.0,
        le=1.0,
        description="小幅度眼动相对风格基准时长的最小缩放：移动幅度趋近 0 时按此比例缩短，"
        "幅度趋近最大时用满基准时长，使小幅看得快、大幅看得慢",
    )
    min_fixation: float = Field(default=0.45, ge=0, description="随机注视停留最短时长")
    max_fixation: float = Field(default=1.6, ge=0, description="随机注视停留最长时长")
    center_bias: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="每次扫视回到中心附近（而非边缘）的概率",
    )
    center_micro_chance: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="本周期采用中心高频轻微扰动的概率；其余周期进入随机注视",
    )
    micro_gaze_x_amplitude: float = Field(
        default=0.16,
        ge=0.0,
        le=1.0,
        description="中心轻微扰动的水平幅度",
    )
    micro_gaze_y_amplitude: float = Field(
        default=0.12,
        ge=0.0,
        le=1.0,
        description="中心轻微扰动的垂直幅度",
    )
    min_micro_duration: float = Field(default=0.018, gt=0.0, description="中心扰动到位最短时长")
    max_micro_duration: float = Field(default=0.045, gt=0.0, description="中心扰动到位最长时长")
    min_micro_fixation: float = Field(default=0.015, ge=0.0, description="中心扰动停留最短时长")
    max_micro_fixation: float = Field(default=0.025, ge=0.0, description="中心扰动停留最长时长")
    balance_window: int = Field(
        default=6,
        ge=0,
        description="左右注视均衡的历史窗口大小：记录最近 N 次水平方向，"
        "采样偏向已有多数侧时按不平衡程度概率翻转，使长短期左右注视频率趋于一致。0 关闭",
    )
    reverse_head_chance: float = Field(
        default=0.18,
        ge=0.0,
        le=1.0,
        description="头部反向跟随的概率：看一侧、头却朝另一侧偏/歪，制造俏皮歪头",
    )
    drift_chance: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="本次眼动为「缓慢漂移」的概率（慢移到新点，像走神/打量）",
    )
    min_drift_duration: float = Field(
        default=0.75,
        gt=0.0,
        description="缓慢漂移到位的最短时长",
    )
    max_drift_duration: float = Field(
        default=2.2,
        gt=0.0,
        description="缓慢漂移到位的最长时长",
    )
    dart_chance: float = Field(
        default=0.08,
        ge=0.0,
        le=1.0,
        description="本次眼动为「快速连扫」的概率（极短到位 + 极短凝视，连续瞟动）",
    )
    min_dart_fixation: float = Field(
        default=0.15,
        ge=0.0,
        description="快速连扫的最短凝视时长",
    )
    max_dart_fixation: float = Field(
        default=0.5,
        ge=0.0,
        description="快速连扫的最长凝视时长",
    )
    priority: int = Field(default=10, description="眼神/头部语义参数控制优先级")

    @model_validator(mode="after")
    def validate_gaze_range(self) -> "GazeControllerSettings":
        if self.max_saccade_duration < self.min_saccade_duration:
            raise ValueError("max_saccade_duration 不能小于 min_saccade_duration")
        if self.max_fixation < self.min_fixation:
            raise ValueError("max_fixation 不能小于 min_fixation")
        if self.max_drift_duration < self.min_drift_duration:
            raise ValueError("max_drift_duration 不能小于 min_drift_duration")
        if self.max_dart_fixation < self.min_dart_fixation:
            raise ValueError("max_dart_fixation 不能小于 min_dart_fixation")
        if self.max_micro_duration < self.min_micro_duration:
            raise ValueError("max_micro_duration 不能小于 min_micro_duration")
        if self.max_micro_fixation < self.min_micro_fixation:
            raise ValueError("max_micro_fixation 不能小于 min_micro_fixation")
        if self.drift_chance + self.dart_chance > 1.0:
            raise ValueError("drift_chance 与 dart_chance 之和不能大于 1.0")
        return self


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
    update_interval: float = Field(default=0.02, gt=0.0, description="更新间隔")
    attack_duration: float = Field(default=0.02, ge=0.0, description="张嘴过渡时长")
    release_duration: float = Field(default=0.04, ge=0.0, description="闭嘴过渡时长")
    priority: int = Field(default=20, description="嘴型参数控制优先级")

    @model_validator(mode="after")
    def validate_mouth_sync_range(self) -> "MouthSyncControllerSettings":
        if self.voice_ceiling <= self.noise_floor:
            raise ValueError("voice_ceiling 必须大于 noise_floor")
        return self


class ExpressionControllerSettings(ControllerSettings):
    """表情解算控制器配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "HEART"})

    au_priority: int = Field(
        default=99,
        description="表情语义缓动的优先级，保持期间高于此值的控制器才能接管参数",
    )
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

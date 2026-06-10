"""表情 AU 解算系统用到的数据模型"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from livestudio.services.semantic_actions import SemanticActionTarget


class EmotionKind(StrEnum):
    """表情解算时支持的归一化情绪类型"""

    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    NEUTRAL = "neutral"


class ExpressionRegion(StrEnum):
    """组成完整表情时会用到的脸部区域"""

    BROW = "brow"
    EYE = "eye"
    MOUTH = "mouth"
    HEAD = "head"


class ExpressionRuleKind(StrEnum):
    """AU 组合规则类型"""

    MUTEX = "mutex"
    SYNERGY = "synergy"
    SUPPRESSION = "suppression"
    DEPENDENCY = "dependency"
    PRESERVE = "preserve"


@dataclass(frozen=True, slots=True)
class ExpressionTarget:
    """AU 里的一个语义动作目标，支持固定值或随机范围"""

    action: str
    value: float | None = None
    value_range: tuple[float, float] | None = None
    weight: float = 1.0
    scale_by_intensity: bool = True
    jitter: float = 0.0

    def __post_init__(self) -> None:
        if (self.value is None) == (self.value_range is None):
            raise ValueError("ExpressionTarget 必须且只能设置 value 或 value_range")
        if self.value_range is not None and self.value_range[1] < self.value_range[0]:
            raise ValueError("ExpressionTarget.value_range 最大值不能小于最小值")


@dataclass(frozen=True, slots=True)
class ExpressionUnit:
    """受 FACS 启发的独立 AU 单元"""

    id: str
    regions: frozenset[ExpressionRegion]
    targets: tuple[ExpressionTarget, ...]
    emotion_correlations: Mapping[EmotionKind, float] = field(default_factory=dict)
    naturalness: float = 1.0
    base_weight: float = 1.0
    priority: int = 40
    easing: str = "in_out_sine"
    activation_threshold: float = 0.12

    def __post_init__(self) -> None:
        if not self.regions:
            raise ValueError("ExpressionUnit.regions 不能为空")
        if not self.targets:
            raise ValueError("ExpressionUnit.targets 不能为空")

    def correlation_for(self, emotion: EmotionKind) -> float:
        return max(-1.0, min(1.0, self.emotion_correlations.get(emotion, 0.0)))


@dataclass(frozen=True, slots=True)
class ExpressionCombinationRule:
    """AU 组合时要遵守的关系规则"""

    id: str
    kind: ExpressionRuleKind = ExpressionRuleKind.MUTEX
    unit_ids: frozenset[str] = frozenset()
    source_unit_id: str | None = None
    target_unit_id: str | None = None
    emotions: frozenset[EmotionKind] = frozenset()
    penalty: float = 0.0
    bonus: float = 0.0
    strength: float = 0.0
    strategy: str = "keep_highest_score"


@dataclass(frozen=True, slots=True)
class ScoredExpressionUnit:
    """带有解算得分和激活强度的 AU"""

    unit: ExpressionUnit
    score: float
    activation: float
    correlation: float
    platform_support: float


@dataclass(frozen=True, slots=True)
class ExpressionSignature:
    """简短记录之前用过的表情，避免一直重复"""

    unit_ids: tuple[str, ...]
    target_values: Mapping[str, float]
    semantic_tags: frozenset[str]
    emotion: EmotionKind
    intensity: float


class EmotionRequest(BaseModel):
    """根据单个归一化情绪强度生成表情的请求"""

    model_config = ConfigDict(extra="forbid")

    emotions: dict[EmotionKind, float] = Field(
        default_factory=lambda: {EmotionKind.NEUTRAL: 1.0},
        description="只能包含一个正向情绪强度，比如 {'joy': 0.8}",
    )
    intensity: float = Field(default=0.7, ge=0.0, le=1.0)
    randomness: float = Field(default=0.25, ge=0.0, le=1.0)
    diversity: float = Field(default=0.35, ge=0.0, le=1.0)
    value_jitter: float = Field(default=0.0, ge=0.0, le=1.0)
    history_avoidance: float = Field(default=0.35, ge=0.0, le=1.0)
    duration_scale: float = Field(default=1.0, gt=0.0)
    min_au_score: float = Field(default=0.18, ge=0.0)
    core_score: float = Field(default=0.62, ge=0.0)
    max_units: int = Field(default=5, ge=1)

    @field_validator("emotions")
    @classmethod
    def validate_emotions(
        cls,
        value: dict[EmotionKind, float],
    ) -> dict[EmotionKind, float]:
        if not value:
            return {EmotionKind.NEUTRAL: 1.0}
        normalized = {
            emotion: max(0.0, min(1.0, weight))
            for emotion, weight in value.items()
            if weight > 0.0
        }
        if not normalized:
            return {EmotionKind.NEUTRAL: 1.0}
        if len(normalized) != 1:
            raise ValueError("EmotionRequest 只能包含一个正向情绪强度")
        return normalized

    @property
    def emotion(self) -> EmotionKind:
        return next(iter(self.emotions))

    @property
    def emotion_strength(self) -> float:
        return next(iter(self.emotions.values()))


@dataclass(frozen=True, slots=True)
class SelectedExpression:
    """按当前请求解算出的一个或多个 AU"""

    units: tuple[ExpressionUnit, ...]
    emotion: EmotionKind
    units_by_region: Mapping[ExpressionRegion, tuple[ExpressionUnit, ...]]
    score: float
    emotion_match: float
    expression_strength: float
    semantic_tags: frozenset[str]
    targets: tuple[SemanticActionTarget, ...]


class ExpressionTargetConfig(BaseModel):
    """模型级 AU 到语义动作的绑定配置"""

    model_config = ConfigDict(extra="forbid")

    action: str
    value: float | None = None
    min: float | None = None
    max: float | None = None
    weight: float = Field(default=1.0, ge=0.0)
    scale_by_intensity: bool = True
    jitter: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_value_source(self) -> ExpressionTargetConfig:
        has_value = self.value is not None
        has_range = self.min is not None or self.max is not None
        if has_value == has_range:
            raise ValueError("AU 绑定必须且只能设置 value 或 min/max")
        if has_range and (self.min is None or self.max is None):
            raise ValueError("AU 绑定范围必须同时设置 min 和 max")
        if self.min is not None and self.max is not None and self.max < self.min:
            raise ValueError("AU 绑定 max 不能小于 min")
        return self

    @classmethod
    def from_target(cls, target: ExpressionTarget) -> ExpressionTargetConfig:
        if target.value_range is not None:
            return cls(
                action=target.action,
                min=target.value_range[0],
                max=target.value_range[1],
                weight=target.weight,
                scale_by_intensity=target.scale_by_intensity,
                jitter=target.jitter,
            )
        return cls(
            action=target.action,
            value=target.value,
            weight=target.weight,
            scale_by_intensity=target.scale_by_intensity,
            jitter=target.jitter,
        )

    def to_target(self) -> ExpressionTarget:
        return ExpressionTarget(
            action=self.action,
            value=self.value,
            value_range=(self.min, self.max) if self.min is not None and self.max is not None else None,
            weight=self.weight,
            scale_by_intensity=self.scale_by_intensity,
            jitter=self.jitter,
        )


class ExpressionUnitConfig(BaseModel):
    """可持久化的模型级 AU 配置"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    regions: list[ExpressionRegion]
    targets: list[ExpressionTargetConfig]
    emotion_correlations: dict[EmotionKind, float] = Field(default_factory=dict)
    naturalness: float = Field(default=1.0, ge=0.0, le=1.0)
    base_weight: float = Field(default=1.0, ge=0.0)
    priority: int = 40
    easing: str = "in_out_sine"
    activation_threshold: float = Field(default=0.12, ge=0.0, le=1.0)

    @field_validator("emotion_correlations")
    @classmethod
    def clamp_correlations(
        cls,
        value: dict[EmotionKind, float],
    ) -> dict[EmotionKind, float]:
        return {emotion: max(-1.0, min(1.0, score)) for emotion, score in value.items()}

    @classmethod
    def from_unit(cls, unit: ExpressionUnit) -> ExpressionUnitConfig:
        return cls(
            enabled=True,
            regions=list(unit.regions),
            targets=[ExpressionTargetConfig.from_target(target) for target in unit.targets],
            emotion_correlations=dict(unit.emotion_correlations),
            naturalness=unit.naturalness,
            base_weight=unit.base_weight,
            priority=unit.priority,
            easing=unit.easing,
            activation_threshold=unit.activation_threshold,
        )

    def to_unit(self, fallback_id: str) -> ExpressionUnit | None:
        if not self.enabled:
            return None
        return ExpressionUnit(
            id=fallback_id,
            regions=frozenset(self.regions),
            targets=tuple(target.to_target() for target in self.targets),
            emotion_correlations=self.emotion_correlations,
            naturalness=self.naturalness,
            base_weight=self.base_weight,
            priority=self.priority,
            easing=self.easing,
            activation_threshold=self.activation_threshold,
        )


class ExpressionRuleConfig(BaseModel):
    """可持久化的 AU 规则配置"""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ExpressionRuleKind = ExpressionRuleKind.MUTEX
    unit_ids: list[str] = Field(default_factory=list)
    source_unit_id: str | None = None
    target_unit_id: str | None = None
    emotions: list[EmotionKind] = Field(default_factory=list)
    penalty: float = 0.0
    bonus: float = 0.0
    strength: float = 0.0
    strategy: str = "keep_highest_score"

    @classmethod
    def from_rule(cls, rule: ExpressionCombinationRule) -> ExpressionRuleConfig:
        return cls(
            id=rule.id,
            kind=rule.kind,
            unit_ids=list(rule.unit_ids),
            source_unit_id=rule.source_unit_id,
            target_unit_id=rule.target_unit_id,
            emotions=list(rule.emotions),
            penalty=rule.penalty,
            bonus=rule.bonus,
            strength=rule.strength,
            strategy=rule.strategy,
        )

    def to_rule(self) -> ExpressionCombinationRule:
        return ExpressionCombinationRule(
            id=self.id,
            kind=self.kind,
            unit_ids=frozenset(self.unit_ids),
            source_unit_id=self.source_unit_id,
            target_unit_id=self.target_unit_id,
            emotions=frozenset(self.emotions),
            penalty=self.penalty,
            bonus=self.bonus,
            strength=self.strength,
            strategy=self.strategy,
        )


class ExpressionRuntimeConfig(BaseModel):
    """模型级表情解算运行时参数"""

    model_config = ConfigDict(extra="forbid")

    max_units: int = Field(default=5, ge=1)
    randomness: float = Field(default=0.25, ge=0.0, le=1.0)
    diversity: float = Field(default=0.35, ge=0.0, le=1.0)
    history_avoidance: float = Field(default=0.35, ge=0.0, le=1.0)
    value_jitter: float = Field(default=0.0, ge=0.0, le=1.0)
    duration_scale: float = Field(default=1.0, gt=0.0)
    min_au_score: float = Field(default=0.18, ge=0.0)
    core_score: float = Field(default=0.62, ge=0.0)
    default_easing: str = "in_out_sine"


class ExpressionProfileConfig(BaseModel):
    """每个 Live2D 模型自己的 AU、规则和运行时配置"""

    model_config = ConfigDict(extra="forbid")

    units: dict[str, ExpressionUnitConfig] = Field(default_factory=dict)
    rules: list[ExpressionRuleConfig] = Field(default_factory=list)
    runtime: ExpressionRuntimeConfig = Field(default_factory=ExpressionRuntimeConfig)

    def to_units(self) -> tuple[ExpressionUnit, ...]:
        units: list[ExpressionUnit] = []
        for unit_id, config in self.units.items():
            unit = config.to_unit(unit_id)
            if unit is not None:
                units.append(unit)
        return tuple(units)

    def to_rules(self) -> tuple[ExpressionCombinationRule, ...]:
        return tuple(rule.to_rule() for rule in self.rules)

    def ensure_defaults(self, defaults: ExpressionProfileConfig) -> bool:
        changed = False
        for unit_id, unit in defaults.units.items():
            if unit_id not in self.units:
                self.units[unit_id] = unit.model_copy(deep=True)
                changed = True

        existing_rule_ids = {rule.id for rule in self.rules}
        for rule in defaults.rules:
            if rule.id not in existing_rule_ids:
                self.rules.append(rule.model_copy(deep=True))
                changed = True

        return changed

    def request_with_runtime_defaults(self, request: EmotionRequest) -> EmotionRequest:
        runtime = self.runtime
        return request.model_copy(
            update={
                "randomness": request.randomness if request.randomness != 0.25 else runtime.randomness,
                "diversity": request.diversity if request.diversity != 0.35 else runtime.diversity,
                "value_jitter": request.value_jitter if request.value_jitter != 0.0 else runtime.value_jitter,
                "history_avoidance": request.history_avoidance
                if request.history_avoidance != 0.35
                else runtime.history_avoidance,
                "duration_scale": request.duration_scale if request.duration_scale != 1.0 else runtime.duration_scale,
                "min_au_score": request.min_au_score if request.min_au_score != 0.18 else runtime.min_au_score,
                "core_score": request.core_score if request.core_score != 0.62 else runtime.core_score,
                "max_units": request.max_units if request.max_units != 5 else runtime.max_units,
            },
        )


def units_by_region(
    units: Iterable[ExpressionUnit],
) -> dict[ExpressionRegion, tuple[ExpressionUnit, ...]]:
    by_region: dict[ExpressionRegion, list[ExpressionUnit]] = {}
    for unit in units:
        for region in unit.regions:
            by_region.setdefault(region, []).append(unit)
    return {region: tuple(region_units) for region, region_units in by_region.items()}

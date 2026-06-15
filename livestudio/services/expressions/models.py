"""表情系统用到的数据模型"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EmotionKind(StrEnum):
    """选表情时支持的情绪类型"""

    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    NEUTRAL = "neutral"


class ExpressionRegion(StrEnum):
    """组成完整表情时会用到的脸部区域"""

    BROW = "brow"
    EYE = "eye"
    MOUTH = "mouth"
    HEAD = "head"


@dataclass(frozen=True, slots=True)
class ExpressionTarget:
    """表情单元里的一个语义动作目标，支持固定值或随机范围"""

    action: str
    value: float | None = None
    value_range: tuple[float, float] | None = None
    weight: float = 1.0
    scale_by_intensity: bool = True
    jitter: float = 0.0

@dataclass(frozen=True, slots=True)
class ExpressionUnit:
    """可以重复使用的脸部动作单元，参考了 FACS 的动作单元"""

    id: str
    regions: frozenset[ExpressionRegion]
    targets: tuple[ExpressionTarget, ...]
    naturalness: float = 1.0
    base_weight: float = 1.0
    priority: int = 40
    easing: str = "in_out_sine"

@dataclass(frozen=True, slots=True)
class ExpressionCombinationRule:
    """表情动作组合时要遵守的全局兼容规则"""

    id: str
    required_unit_ids: frozenset[str] = frozenset()
    excluded_unit_ids: frozenset[str] = frozenset()
    any_of_unit_ids: frozenset[str] = frozenset()
    emotions: frozenset[EmotionKind] = frozenset()
    penalty: float = 0.0
    bonus: float = 0.0


@dataclass(frozen=True, slots=True)
class ScoredExpressionUnit:
    """带有选择得分的表情动作单元"""

    unit: ExpressionUnit
    score: float
    template_weight: float
    platform_support: float


@dataclass(frozen=True, slots=True)
class ExpressionSignature:
    """简短记录之前用过的表情，避免一直重复"""

    unit_ids: tuple[str, ...]
    target_values: Mapping[str, float]
    semantic_tags: frozenset[str]
    dominant_emotion: EmotionKind
    intensity: float


class EmotionRequest(BaseModel):
    """根据情绪数值生成表情的请求"""

    model_config = ConfigDict(extra="forbid")

    emotions: dict[EmotionKind, float] = Field(
        default_factory=lambda: {EmotionKind.NEUTRAL: 1.0},
        description="用来挑选表情动作的情绪数值",
    )
    intent: str | None = Field(
        default=None,
        description="可选的组合表情意图，比如 阴险笑、苦笑",
    )
    intensity: float = Field(default=0.7, ge=0.0, le=1.0)
    randomness: float = Field(default=0.25, ge=0.0, le=1.0)
    value_jitter: float = Field(default=0.0, ge=0.0, le=1.0)
    history_avoidance: float = Field(default=0.35, ge=0.0, le=1.0)
    duration_scale: float = Field(default=1.0, gt=0.0)
    min_intent_score: float = Field(default=0.28, ge=0.0)
    max_units: int = Field(default=99, ge=1)

@dataclass(frozen=True, slots=True)
class SelectedExpression:
    """按当前请求选出的一个或多个表情动作"""

    units: tuple[ExpressionUnit, ...]
    intent_id: str | None
    units_by_region: Mapping[ExpressionRegion, tuple[ExpressionUnit, ...]]
    score: float
    intent_match: float
    expression_strength: float
    semantic_tags: frozenset[str]
    targets: tuple[ExpressionTarget, ...]

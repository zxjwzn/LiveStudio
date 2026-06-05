"""表情系统用到的数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from livestudio.services.semantic_actions import SemanticActionTarget


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
class ExpressionUnit:
    """可以重复使用的脸部动作单元，参考了 FACS 的动作单元"""

    id: str
    region: ExpressionRegion
    targets: tuple[SemanticActionTarget, ...]
    emotions: Mapping[EmotionKind, float]
    intensity: float
    naturalness: float = 1.0
    base_weight: float = 1.0
    tags: frozenset[str] = frozenset()
    conflicts: frozenset[str] = frozenset()
    soft_conflicts: Mapping[str, float] = field(default_factory=dict)
    synergies: Mapping[str, float] = field(default_factory=dict)
    value_jitter: float = 0.0
    jitter_by_action: Mapping[str, float] = field(default_factory=dict)
    duration: float = 0.35
    priority: int = 40
    easing: str = "in_out_sine"


@dataclass(frozen=True, slots=True)
class ExpressionCombinationRule:
    """表情动作组合时要遵守的兼容规则"""

    id: str
    emotions: frozenset[EmotionKind] = frozenset()
    require_tags: frozenset[str] = frozenset()
    forbid_tags: frozenset[str] = frozenset()
    require_unit_ids: frozenset[str] = frozenset()
    forbid_unit_ids: frozenset[str] = frozenset()
    penalty: float = 1.0


@dataclass(frozen=True, slots=True)
class ExpressionSignature:
    """简短记录之前用过的表情，避免一直重复"""

    unit_ids: tuple[str, ...]
    target_values: Mapping[str, float]
    dominant_emotion: EmotionKind
    intensity: float


class EmotionRequest(BaseModel):
    """根据情绪数值生成表情的请求"""

    model_config = ConfigDict(extra="forbid")

    emotions: dict[EmotionKind, float] = Field(
        default_factory=lambda: {EmotionKind.NEUTRAL: 1.0},
        description="用来挑选表情动作的情绪数值",
    )
    intensity: float = Field(default=0.7, ge=0.0, le=1.0)
    randomness: float = Field(default=0.25, ge=0.0, le=1.0)
    value_jitter: float = Field(default=0.0, ge=0.0, le=1.0)
    history_avoidance: float = Field(default=0.35, ge=0.0, le=1.0)
    duration_scale: float = Field(default=1.0, gt=0.0)
    allow_none_regions: bool = True

    @field_validator("emotions")
    @classmethod
    def validate_emotions(
        cls,
        value: dict[EmotionKind, float],
    ) -> dict[EmotionKind, float]:
        if not value:
            return {EmotionKind.NEUTRAL: 1.0}
        return {
            emotion: max(0.0, min(1.0, weight))
            for emotion, weight in value.items()
            if weight > 0.0
        } or {EmotionKind.NEUTRAL: 1.0}


@dataclass(frozen=True, slots=True)
class ScoredExpressionUnit:
    """带有选择得分的表情动作单元"""

    unit: ExpressionUnit
    score: float
    emotion_match: float
    platform_support: float


@dataclass(frozen=True, slots=True)
class SelectedExpression:
    """由各脸部区域动作组成的已选表情"""

    units: Mapping[ExpressionRegion, ExpressionUnit]
    score: float
    emotion_match: float
    targets: tuple[SemanticActionTarget, ...]

"""Expression system domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmotionKind(StrEnum):
    """Supported emotion categories for expression selection."""

    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    NEUTRAL = "neutral"


class ExpressionRegion(StrEnum):
    """Facial regions used to compose a complete expression."""

    BROW = "brow"
    EYE = "eye"
    MOUTH = "mouth"
    HEAD = "head"


class SemanticParameter(StrEnum):
    """Model-independent expression parameter names."""

    BROW_INNER_UP = "brow.inner_up"
    BROW_OUTER_UP = "brow.outer_up"
    BROW_DOWN = "brow.down"
    EYE_OPEN = "eye.open"
    EYE_SQUINT = "eye.squint"
    EYE_WIDE = "eye.wide"
    MOUTH_OPEN = "mouth.open"
    MOUTH_SMILE = "mouth.smile"
    MOUTH_FROWN = "mouth.frown"
    MOUTH_PUCKER = "mouth.pucker"
    HEAD_YAW = "head.yaw"
    HEAD_PITCH = "head.pitch"
    HEAD_ROLL = "head.roll"


@dataclass(frozen=True, slots=True)
class UnitTarget:
    """A semantic parameter target in an expression unit."""

    semantic_param: str
    value: float
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class ExpressionUnit:
    """A reusable facial action unit inspired by FACS action units."""

    id: str
    region: ExpressionRegion
    targets: tuple[UnitTarget, ...]
    emotions: Mapping[EmotionKind, float]
    intensity: float
    naturalness: float = 1.0
    base_weight: float = 1.0
    tags: frozenset[str] = frozenset()
    conflicts: frozenset[str] = frozenset()
    synergies: Mapping[str, float] = field(default_factory=dict)
    duration: float = 0.35
    priority: int = 40
    easing: str = "in_out_sine"

    def __post_init__(self) -> None:
        object.__setattr__(self, "emotions", MappingProxyType(dict(self.emotions)))
        object.__setattr__(self, "synergies", MappingProxyType(dict(self.synergies)))


class EmotionRequest(BaseModel):
    """A request to synthesize an expression from an emotion vector."""

    model_config = ConfigDict(extra="forbid")

    emotions: dict[EmotionKind, float] = Field(
        default_factory=lambda: {EmotionKind.NEUTRAL: 1.0},
        description="Emotion vector used to select expression units.",
    )
    intensity: float = Field(default=0.7, ge=0.0, le=1.0)
    randomness: float = Field(default=0.25, ge=0.0, le=1.0)
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
    """An expression unit with the selector score that produced it."""

    unit: ExpressionUnit
    score: float
    emotion_match: float
    calibration_support: float


@dataclass(frozen=True, slots=True)
class SelectedExpression:
    """A selected facial expression composed from regional units."""

    units: Mapping[ExpressionRegion, ExpressionUnit]
    score: float
    emotion_match: float
    targets: tuple[UnitTarget, ...]

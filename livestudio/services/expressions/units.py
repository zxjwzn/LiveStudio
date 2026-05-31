"""Built-in expression units."""

from __future__ import annotations

from livestudio.services.semantic_actions import SemanticAction, SemanticActionTarget

from .models import (
    EmotionKind,
    ExpressionRegion,
    ExpressionUnit,
)


def _target(
    action: SemanticAction,
    value: float,
    weight: float = 1.0,
) -> SemanticActionTarget:
    return SemanticActionTarget(action.value, value, weight)


BUILTIN_EXPRESSION_UNITS: tuple[ExpressionUnit, ...] = (
    ExpressionUnit(
        id="brow_none",
        region=ExpressionRegion.BROW,
        targets=(),
        emotions={EmotionKind.NEUTRAL: 1.0},
        intensity=0.0,
        tags=frozenset({"none"}),
    ),
    ExpressionUnit(
        id="brow_inner_up_soft",
        region=ExpressionRegion.BROW,
        targets=(_target(SemanticAction.BROW_RAISE, 0.45),),
        emotions={
            EmotionKind.SADNESS: 0.8,
        },
        intensity=0.45,
        naturalness=0.9,
        tags=frozenset({"soft", "vulnerable"}),
    ),
    ExpressionUnit(
        id="brow_down_tense",
        region=ExpressionRegion.BROW,
        targets=(_target(SemanticAction.BROW_LOWER, 0.65),),
        emotions={
            EmotionKind.ANGER: 0.9,
        },
        intensity=0.65,
        naturalness=0.75,
        tags=frozenset({"tense"}),
        conflicts=frozenset({"soft"}),
    ),
    ExpressionUnit(
        id="brow_outer_up_wide",
        region=ExpressionRegion.BROW,
        targets=(_target(SemanticAction.BROW_RAISE, 0.75),),
        emotions={EmotionKind.NEUTRAL: 0.2},
        intensity=0.75,
        naturalness=0.75,
        tags=frozenset({"wide", "alert"}),
    ),
    ExpressionUnit(
        id="eye_none",
        region=ExpressionRegion.EYE,
        targets=(),
        emotions={EmotionKind.NEUTRAL: 1.0},
        intensity=0.0,
        tags=frozenset({"none"}),
    ),
    ExpressionUnit(
        id="eye_smile_soft",
        region=ExpressionRegion.EYE,
        targets=(_target(SemanticAction.EYE_CLOSE, 0.35),),
        emotions={
            EmotionKind.JOY: 0.75,
        },
        intensity=0.35,
        naturalness=0.95,
        tags=frozenset({"soft", "friendly"}),
        synergies={"mouth_smile_soft": 0.3, "mouth_smile_bright": 0.25},
    ),
    ExpressionUnit(
        id="eye_wide_alert",
        region=ExpressionRegion.EYE,
        targets=(_target(SemanticAction.EYE_WIDEN, 0.75),),
        emotions={EmotionKind.NEUTRAL: 0.2},
        intensity=0.75,
        naturalness=0.7,
        tags=frozenset({"wide", "alert"}),
    ),
    ExpressionUnit(
        id="eye_narrow_suspicious",
        region=ExpressionRegion.EYE,
        targets=(_target(SemanticAction.EYE_CLOSE, 0.65),),
        emotions={
            EmotionKind.ANGER: 0.55,
        },
        intensity=0.65,
        naturalness=0.8,
        tags=frozenset({"tense", "suspicious"}),
    ),
    ExpressionUnit(
        id="mouth_none",
        region=ExpressionRegion.MOUTH,
        targets=(),
        emotions={EmotionKind.NEUTRAL: 1.0},
        intensity=0.0,
        tags=frozenset({"none"}),
    ),
    ExpressionUnit(
        id="mouth_smile_soft",
        region=ExpressionRegion.MOUTH,
        targets=(
            _target(SemanticAction.MOUTH_SMILE, 0.45),
            _target(SemanticAction.MOUTH_OPEN, 0.08, 0.4),
        ),
        emotions={
            EmotionKind.JOY: 0.8,
        },
        intensity=0.45,
        naturalness=0.95,
        tags=frozenset({"soft", "friendly"}),
        synergies={"eye_smile_soft": 0.3},
    ),
    ExpressionUnit(
        id="mouth_smile_bright",
        region=ExpressionRegion.MOUTH,
        targets=(
            _target(SemanticAction.MOUTH_SMILE, 0.85),
            _target(SemanticAction.MOUTH_OPEN, 0.22, 0.6),
        ),
        emotions={
            EmotionKind.JOY: 0.95,
        },
        intensity=0.85,
        naturalness=0.75,
        tags=frozenset({"bright", "friendly"}),
    ),
    ExpressionUnit(
        id="mouth_frown_soft",
        region=ExpressionRegion.MOUTH,
        targets=(
            _target(SemanticAction.MOUTH_FROWN, 0.55),
            _target(SemanticAction.MOUTH_OPEN, 0.04, 0.3),
        ),
        emotions={EmotionKind.SADNESS: 0.8},
        intensity=0.55,
        naturalness=0.85,
        tags=frozenset({"soft", "down"}),
        conflicts=frozenset({"friendly"}),
    ),
    ExpressionUnit(
        id="mouth_tense_hard",
        region=ExpressionRegion.MOUTH,
        targets=(
            _target(SemanticAction.MOUTH_FROWN, 0.45),
            _target(SemanticAction.MOUTH_OPEN, 0.06, 0.4),
        ),
        emotions={EmotionKind.ANGER: 0.35},
        intensity=0.65,
        naturalness=0.7,
        tags=frozenset({"tense"}),
        conflicts=frozenset({"friendly"}),
    ),
    ExpressionUnit(
        id="mouth_anger_tense",
        region=ExpressionRegion.MOUTH,
        targets=(
            _target(SemanticAction.MOUTH_FROWN, 0.7),
            _target(SemanticAction.MOUTH_OPEN, 0.08, 0.45),
        ),
        emotions={EmotionKind.ANGER: 0.85},
        intensity=0.7,
        naturalness=0.75,
        tags=frozenset({"tense", "down"}),
        conflicts=frozenset({"friendly", "soft"}),
    ),
    ExpressionUnit(
        id="head_none",
        region=ExpressionRegion.HEAD,
        targets=(),
        emotions={EmotionKind.NEUTRAL: 1.0},
        intensity=0.0,
        tags=frozenset({"none"}),
    ),
    ExpressionUnit(
        id="head_tilt_soft",
        region=ExpressionRegion.HEAD,
        targets=(
            _target(SemanticAction.HEAD_ROLL, 0.35),
            _target(SemanticAction.HEAD_PITCH, -0.12, 0.5),
        ),
        emotions={
            EmotionKind.JOY: 0.35,
            EmotionKind.SADNESS: 0.25,
        },
        intensity=0.35,
        naturalness=0.9,
        tags=frozenset({"soft", "settled"}),
    ),
    ExpressionUnit(
        id="head_forward_alert",
        region=ExpressionRegion.HEAD,
        targets=(_target(SemanticAction.HEAD_PITCH, 0.35),),
        emotions={
            EmotionKind.ANGER: 0.45,
        },
        intensity=0.4,
        naturalness=0.8,
        tags=frozenset({"alert"}),
    ),
    ExpressionUnit(
        id="head_avert_down",
        region=ExpressionRegion.HEAD,
        targets=(
            _target(SemanticAction.HEAD_YAW, -0.35),
            _target(SemanticAction.HEAD_PITCH, -0.18, 0.6),
        ),
        emotions={EmotionKind.SADNESS: 0.35},
        intensity=0.45,
        naturalness=0.85,
        tags=frozenset({"soft", "averted"}),
    ),
)


BUILTIN_UNITS_BY_ID = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}

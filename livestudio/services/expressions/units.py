"""内置的表情动作单元"""

from __future__ import annotations

from livestudio.services.semantic_actions import SemanticAction

from .models import (
    EmotionKind,
    EmotionProfile,
    ExpressionRegion,
    ExpressionTarget,
    ExpressionUnit,
)


def _target(
    action: SemanticAction,
    *,
    value: float | None = None,
    value_range: tuple[float, float] | None = None,
    weight: float = 1.0,
    scale_by_intensity: bool = True,
    jitter: float = 0.0,
) -> ExpressionTarget:
    return ExpressionTarget(
        action=action.value,
        value=value,
        value_range=value_range,
        weight=weight,
        scale_by_intensity=scale_by_intensity,
        jitter=jitter,
    )


def _profile(
    weight: float,
    *tags: str,
    intensity: float | None = None,
) -> EmotionProfile:
    return EmotionProfile(
        weight=weight,
        tags=frozenset(tags),
        intensity=intensity,
    )


BUILTIN_EXPRESSION_UNITS: tuple[ExpressionUnit, ...] = (
    ExpressionUnit(
        id="brow_knit",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(
            _target(SemanticAction.BROW_HEIGHT, value_range=(0.0, 0.18), jitter=0.03),
        ),
        emotions={
            EmotionKind.ANGER: _profile(
                0.95,
                "anger",
                "brow_knit",
                "tense",
                "focused",
                intensity=0.75,
            ),
            EmotionKind.SADNESS: _profile(
                1,
                "sadness",
                "brow_knit",
                "pained",
                intensity=0.75,
            ),
        },
        naturalness=0.82,
        conflicts=frozenset({"brow_raise"}),
    ),
    ExpressionUnit(
        id="brow_raise_soft",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(
            _target(SemanticAction.BROW_HEIGHT, value_range=(0.62, 0.82), jitter=0.05),
        ),
        emotions={
            EmotionKind.SADNESS: _profile(
                0.75,
                "sadness",
                "brow_raise",
                "vulnerable",
                "soft",
                intensity=0.5,
            ),
            EmotionKind.JOY: _profile(
                0.25,
                "joy",
                "brow_raise",
                "open",
                intensity=0.35,
            ),
        },
        naturalness=0.88,
        conflicts=frozenset({"brow_knit"}),
    ),
    ExpressionUnit(
        id="eye_narrow",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_OPEN, value_range=(0.1, 0.4), jitter=0.03),
        ),
        emotions={
            EmotionKind.ANGER: _profile(
                1,
                "anger",
                "eye_narrow",
                "tense",
                intensity=0.7,
            ),
            EmotionKind.JOY: _profile(
                1,
                "joy",
                "eye_narrow",
                "mischievous",
                intensity=1.0,
            ),
        },
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="mouth_smile",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.8, 1), jitter=0.08),
            _target(
                SemanticAction.MOUTH_OPEN,
                value_range=(0.0, 0.3),
                weight=0.45,
                jitter=0.03,
            ),
        ),
        emotions={
            EmotionKind.JOY: _profile(0.96, "joy", "smile", "bright", intensity=0.65),
        },
        naturalness=0.92,
        conflicts=frozenset({"mouth_down", "mouth_press"}),
        synergies={"eye_smile": 0.16},
    ),
    ExpressionUnit(
        id="mouth_down",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.0, 0.2), jitter=0.02),
            _target(
                SemanticAction.MOUTH_OPEN,
                value_range=(0.00, 0.3),
                weight=0.35,
                jitter=0.02,
            ),
        ),
        emotions={
            EmotionKind.SADNESS: _profile(
                0.86,
                "sadness",
                "mouth_down",
                "restrained",
                intensity=0.55,
            ),
            EmotionKind.ANGER: _profile(
                0.8,
                "anger",
                "mouth_down",
                "displeased",
                intensity=0.6,
            ),
        },
        naturalness=0.88,
        conflicts=frozenset({"smile"}),
    ),
    ExpressionUnit(
        id="mouth_sinister_smile",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.55, 0.85), jitter=0.05),
            _target(
                SemanticAction.MOUTH_OPEN,
                value_range=(0.0, 0.08),
                weight=0.45,
                jitter=0.02,
            ),
        ),
        emotions={
            EmotionKind.JOY: _profile(
                0.42,
                "joy",
                "smile",
                "mischievous",
                "sinister",
                intensity=0.8,
            ),
            EmotionKind.ANGER: _profile(
                0.62,
                "anger",
                "smile",
                "sinister",
                "threatening",
                intensity=0.8,
            ),
        },
        naturalness=0.78,
        conflicts=frozenset({"mouth_down", "mouth_press", "bright"}),
        synergies={"eye_narrow": 0.14, "gaze_up_white": 0.12, "head_down_mischievous": 0.12},
    ),
    ExpressionUnit(
        id="mouth_press",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.5, 0.5), jitter=0.02),
            _target(
                SemanticAction.MOUTH_OPEN,
                value_range=(0.00, 0.03),
                weight=0.45,
                jitter=0.02,
            ),
        ),
        emotions={
            EmotionKind.ANGER: _profile(
                0.78,
                "anger",
                "mouth_press",
                "tense",
                intensity=0.7,
            ),
            EmotionKind.SADNESS: _profile(
                0.68,
                "sadness",
                "mouth_press",
                "held_back",
                intensity=0.55,
            ),
        },
        naturalness=0.78,
        conflicts=frozenset({"smile"}),
    ),
    ExpressionUnit(
        id="head_tilt",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_ROLL, value_range=(-0.32, 0.32), jitter=0.04),
            _target(
                SemanticAction.HEAD_PITCH,
                value_range=(-0.1, 0.1),
                weight=0.45,
                jitter=0.03,
            ),
        ),
        emotions={
            EmotionKind.JOY: _profile(
                0.45,
                "joy",
                "head_tilt",
                "lively",
                intensity=0.45,
            ),
            EmotionKind.SADNESS: _profile(
                0.25,
                "sadness",
                "head_tilt",
                "soft",
                intensity=0.4,
            ),
        },
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="head_down_averted",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_YAW, value_range=(-0.5, 0.5), jitter=0.04),
            _target(
                SemanticAction.HEAD_PITCH,
                value_range=(-0.28, -0.08),
                weight=0.65,
                jitter=0.03,
            ),
        ),
        emotions={
            EmotionKind.SADNESS: _profile(
                0.68,
                "sadness",
                "head_down",
                "averted",
                intensity=0.5,
            ),
        },
        naturalness=0.84,
    ),
    ExpressionUnit(
        id="head_forward",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_PITCH, value_range=(-0.5, 0.5), jitter=0.04),
        ),
        emotions={
            EmotionKind.ANGER: _profile(
                0.52,
                "anger",
                "head_forward",
                "alert",
                intensity=0.55,
            ),
        },
        naturalness=0.8,
    ),
    ExpressionUnit(
        id="head_down_mischievous",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_PITCH, value_range=(-0.38, -0.16), jitter=0.04),
            _target(SemanticAction.HEAD_ROLL, value_range=(-0.12, 0.12), weight=0.35, jitter=0.03),
        ),
        emotions={
            EmotionKind.JOY: _profile(
                0.25,
                "joy",
                "mischievous",
                "sinister",
                "head_down",
                intensity=1.0,
            ),
            EmotionKind.ANGER: _profile(
                0.48,
                "anger",
                "sinister",
                "threatening",
                "head_down",
                intensity=0.75,
            ),
        },
        naturalness=0.72,
        conflicts=frozenset({"head_forward", "head_tilt", "head_down"}),
        synergies={"gaze_up_white": 0.18, "mouth_smile": 0.12},
    ),
    ExpressionUnit(
        id="gaze_averted_down",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_X, value_range=(-0.7, -0.4), jitter=0.04),
            _target(SemanticAction.EYE_GAZE_Y, value_range=(-0.6, -0.3), jitter=0.04),
        ),
        emotions={
            EmotionKind.SADNESS: _profile(
                1,
                "sadness",
                "gaze_averted",
                "down",
                intensity=0.7,
            ),
        },
        naturalness=0.75,
    ),
    ExpressionUnit(
        id="gaze_up_white",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_X, value_range=(-0.08, 0.08), jitter=0.03),
            _target(SemanticAction.EYE_GAZE_Y, value_range=(0.35, 0.75), jitter=0.05),
        ),
        emotions={
            EmotionKind.JOY: _profile(
                0.25,
                "joy",
                "mischievous",
                "white_eye",
                "sinister",
                intensity=1.0,
            ),
            EmotionKind.ANGER: _profile(
                0.5,
                "anger",
                "white_eye",
                "threatening",
                intensity=0.8,
            ),
        },
        naturalness=0.68,
        conflicts=frozenset({"gaze_averted", "down"}),
        synergies={"head_down_mischievous": 0.18, "eye_narrow": 0.1},
    ),
)


BUILTIN_UNITS_BY_ID = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}

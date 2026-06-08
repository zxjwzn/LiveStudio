"""内置的表情动作单元"""

from __future__ import annotations

from livestudio.services.semantic_actions import SemanticAction

from .models import (
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


BUILTIN_EXPRESSION_UNITS: tuple[ExpressionUnit, ...] = (
    ExpressionUnit(
        id="brow_knit",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(
            _target(SemanticAction.BROW_HEIGHT, value_range=(0.0, 0.18), jitter=0.03),
        ),
        action_tags=frozenset({"brow_knit", "brow_lower", "tense"}),
        naturalness=0.82,
        conflicts=frozenset({"brow_raise"}),
    ),
    ExpressionUnit(
        id="brow_raise_soft",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(
            _target(SemanticAction.BROW_HEIGHT, value_range=(0.62, 0.82), jitter=0.05),
        ),
        action_tags=frozenset({"brow_raise", "open", "soft"}),
        naturalness=0.88,
        conflicts=frozenset({"brow_knit"}),
    ),
    ExpressionUnit(
        id="eye_closed",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_OPEN, value_range=(0.0, 0.12), jitter=0.02),
        ),
        action_tags=frozenset({"eye_closed", "closed", "soft"}),
        naturalness=0.86,
        conflicts=frozenset({"eye_narrow", "eye_open"}),
    ),
    ExpressionUnit(
        id="eye_narrow",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_OPEN, value_range=(0.1, 0.4), jitter=0.03),
        ),
        action_tags=frozenset({"eye_narrow", "squint"}),
        naturalness=0.82,
        conflicts=frozenset({"eye_closed", "eye_open"}),
    ),
    ExpressionUnit(
        id="eye_open",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_OPEN, value_range=(0.75, 1.0), jitter=0.04),
        ),
        action_tags=frozenset({"eye_open", "wide", "alert"}),
        naturalness=0.84,
        conflicts=frozenset({"eye_closed", "eye_narrow"}),
    ),
    ExpressionUnit(
        id="mouth_corner_up",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.78, 1.0), jitter=0.08),
        ),
        action_tags=frozenset({"mouth_corner_up", "mouth_smile", "smile"}),
        naturalness=0.92,
        conflicts=frozenset({"mouth_corner_down"}),
        synergies={"eye_narrow": 0.08},
    ),
    ExpressionUnit(
        id="mouth_corner_down",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.0, 0.2), jitter=0.02),
        ),
        action_tags=frozenset(
            {"mouth_corner_down", "mouth_down", "frown", "restrained"},
        ),
        naturalness=0.88,
        conflicts=frozenset({"mouth_corner_up", "smile", "mouth_smile"}),
    ),
    ExpressionUnit(
        id="mouth_corner_flat",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.42, 0.58), jitter=0.02),
        ),
        action_tags=frozenset({"mouth_corner_flat", "flat_mouth", "restrained"}),
        naturalness=0.86,
        soft_conflicts={"mouth_corner_up": 0.12, "mouth_corner_down": 0.12},
    ),
    ExpressionUnit(
        id="mouth_closed",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_OPEN, value_range=(0.0, 0.06), jitter=0.01),
        ),
        action_tags=frozenset({"mouth_closed", "closed"}),
        naturalness=0.9,
        conflicts=frozenset({"mouth_slight_open", "mouth_open_wide"}),
    ),
    ExpressionUnit(
        id="mouth_slight_open",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_OPEN, value_range=(0.15, 0.38), jitter=0.03),
        ),
        action_tags=frozenset({"mouth_slight_open", "mouth_open", "mouth_open_soft"}),
        naturalness=0.9,
        conflicts=frozenset({"mouth_closed", "mouth_open_wide"}),
    ),
    ExpressionUnit(
        id="mouth_open_wide",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_OPEN, value_range=(0.6, 1.0), jitter=0.05),
        ),
        action_tags=frozenset({"mouth_open_wide", "mouth_open", "wide"}),
        naturalness=0.76,
        conflicts=frozenset({"mouth_closed", "mouth_slight_open"}),
    ),
    ExpressionUnit(
        id="mouth_press",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.42, 0.56), jitter=0.02),
            _target(
                SemanticAction.MOUTH_OPEN,
                value_range=(0.0, 0.04),
                weight=0.8,
                jitter=0.01,
            ),
        ),
        action_tags=frozenset({"mouth_press", "pressed", "tense", "mouth_closed"}),
        naturalness=0.78,
        soft_conflicts={"mouth_corner_up": 0.18, "mouth_corner_down": 0.12},
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
        action_tags=frozenset({"head_tilt", "lively", "soft"}),
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
        action_tags=frozenset({"head_down", "averted"}),
        naturalness=0.84,
    ),
    ExpressionUnit(
        id="head_forward",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_PITCH, value_range=(-0.5, 0.5), jitter=0.04),
        ),
        action_tags=frozenset({"head_forward", "alert"}),
        naturalness=0.8,
    ),
    ExpressionUnit(
        id="head_down_mischievous",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_PITCH, value_range=(-0.38, -0.16), jitter=0.04),
            _target(
                SemanticAction.HEAD_ROLL,
                value_range=(-0.12, 0.12),
                weight=0.35,
                jitter=0.03,
            ),
        ),
        action_tags=frozenset({"head_down", "mischievous", "threatening"}),
        conflicts=frozenset({"head_forward", "head_tilt", "head_down"}),
        synergies={"gaze_up_white": 0.18, "mouth_corner_up": 0.12},
        naturalness=0.72,
    ),
    ExpressionUnit(
        id="gaze_averted_down",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_X, value_range=(-0.7, -0.4), jitter=0.04),
            _target(SemanticAction.EYE_GAZE_Y, value_range=(-0.6, -0.3), jitter=0.04),
        ),
        action_tags=frozenset({"gaze_averted", "down"}),
        naturalness=0.75,
    ),
    ExpressionUnit(
        id="gaze_up_white",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_X, value_range=(-0.08, 0.08), jitter=0.03),
            _target(SemanticAction.EYE_GAZE_Y, value_range=(0.35, 0.75), jitter=0.05),
        ),
        action_tags=frozenset({"gaze_up", "white_eye", "threatening"}),
        conflicts=frozenset({"gaze_averted", "down"}),
        synergies={"head_down_mischievous": 0.18, "eye_narrow": 0.1},
        naturalness=0.68,
    ),
)


BUILTIN_UNITS_BY_ID = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}

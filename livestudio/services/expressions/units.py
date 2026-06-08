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
        id="皱眉",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(_target(SemanticAction.BROW_HEIGHT, value_range=(0.00, 0.10), jitter=0.10),),
        naturalness=0.72,
    ),
    ExpressionUnit(
        id="轻微抬眉",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(_target(SemanticAction.BROW_HEIGHT, value_range=(0.50, 0.70), jitter=0.10),),
        naturalness=0.88,
    ),
    ExpressionUnit(
        id="抬眉",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(_target(SemanticAction.BROW_HEIGHT, value_range=(0.70, 1.00), jitter=0.10),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="闭眼",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(_target(SemanticAction.EYE_OPEN, value_range=(0.00, 0.10), jitter=0.10),),
        naturalness=0.86,
    ),
    ExpressionUnit(
        id="眯眼",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(_target(SemanticAction.EYE_OPEN, value_range=(0.10, 0.40), jitter=0.10),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="睁眼",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(_target(SemanticAction.EYE_OPEN, value_range=(0.75, 1.00), jitter=0.10),),
        naturalness=0.84,
    ),
    ExpressionUnit(
        id="眼睛居中",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_X, value_range=(-0.08, 0.08), jitter=0.10),
            _target(SemanticAction.EYE_GAZE_Y, value_range=(-0.08, 0.08), jitter=0.10),
        ),
        naturalness=0.92,
    ),
    ExpressionUnit(
        id="眼睛左看",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(_target(SemanticAction.EYE_GAZE_X, value_range=(-1.00, -0.70), jitter=0.10),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="眼睛右看",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(_target(SemanticAction.EYE_GAZE_X, value_range=(0.70, 1.00), jitter=0.10),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="眼睛下看",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(_target(SemanticAction.EYE_GAZE_Y, value_range=(-1.00, -0.70), jitter=0.10),),
        naturalness=0.84,
    ),
    ExpressionUnit(
        id="眼睛上看",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(_target(SemanticAction.EYE_GAZE_Y, value_range=(0.70, 1.00), jitter=0.10),),
        naturalness=0.78,
    ),
    ExpressionUnit(
        id="嘴角上扬",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_SMILE, value_range=(0.60, 1.00), jitter=0.10),),
        naturalness=0.92,
    ),
    ExpressionUnit(
        id="嘴角下压",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_SMILE, value_range=(0.00, 0.40), jitter=0.10),),
        naturalness=0.88,
    ),
    ExpressionUnit(
        id="嘴角平直",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_SMILE, value_range=(0.50, 0.50), jitter=0.10),),
        naturalness=0.86,
    ),
    ExpressionUnit(
        id="闭嘴",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_OPEN, value_range=(0.00, 0.10), jitter=0.10),),
        naturalness=0.9,
    ),
    ExpressionUnit(
        id="嘴巴微张",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_OPEN, value_range=(0.15, 0.40), jitter=0.10),),
        naturalness=0.9,
    ),
    ExpressionUnit(
        id="嘴巴张大",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_OPEN, value_range=(0.60, 1.00), jitter=0.10),),
        naturalness=0.76,
    ),
    ExpressionUnit(
        id="抿嘴",
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
        naturalness=0.78,
    ),
    ExpressionUnit(
        id="嘴部左移",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_X, value_range=(-0.70, -0.25), jitter=0.08),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="嘴部右移",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_X, value_range=(0.25, 0.70), jitter=0.08),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="嘴部上移",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_Y, value_range=(0.25, 0.70), jitter=0.08),),
        naturalness=0.76,
    ),
    ExpressionUnit(
        id="嘴部下移",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(_target(SemanticAction.MOUTH_Y, value_range=(-0.70, -0.25), jitter=0.08),),
        naturalness=0.76,
    ),
    ExpressionUnit(
        id="抬头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(_target(SemanticAction.HEAD_PITCH, value_range=(0.3, 0.7), jitter=0.1),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="低头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(_target(SemanticAction.HEAD_PITCH, value_range=(-0.7, -0.3), jitter=0.10),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="左歪头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(_target(SemanticAction.HEAD_ROLL, value_range=(-0.30, -0.10), jitter=0.10),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="右歪头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(_target(SemanticAction.HEAD_ROLL, value_range=(0.10, 0.30), jitter=0.10),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="左转头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(_target(SemanticAction.HEAD_YAW, value_range=(-0.75, -0.2), jitter=0.10),),
        naturalness=0.82,
    ),
    ExpressionUnit(
        id="右转头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(_target(SemanticAction.HEAD_YAW, value_range=(0.2, 0.75), jitter=0.10),),
        naturalness=0.82,
    ),
)


BUILTIN_UNITS_BY_ID = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}

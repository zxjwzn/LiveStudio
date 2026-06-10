"""内置的 AU 默认定义

这些定义会被写入每个模型的 expression_profile 作为初始配置；
单个模型可以在自己的配置文件里新增、禁用或微调任意 AU。
"""

from __future__ import annotations

from livestudio.services.semantic_actions import SemanticAction

from .models import (
    EmotionKind,
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


def _correlations(**scores: float) -> dict[EmotionKind, float]:
    return {EmotionKind(key): value for key, value in scores.items()}


BUILTIN_EXPRESSION_UNITS: tuple[ExpressionUnit, ...] = (
    ExpressionUnit(
        id="皱眉",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(
            _target(SemanticAction.BROW_HEIGHT, value_range=(0.00, 0.10), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            anger=0.88, sadness=0.85, fear=0.35, joy=-0.72, surprise=-0.25
        ),
        naturalness=0.72,
        priority=62,
        activation_threshold=0.15,
    ),
    ExpressionUnit(
        id="轻微抬眉",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(
            _target(SemanticAction.BROW_HEIGHT, value_range=(0.50, 0.70), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            joy=0.28, surprise=0.45, fear=0.20, anger=-0.25
        ),
        naturalness=0.88,
        priority=45,
        activation_threshold=0.22,
    ),
    ExpressionUnit(
        id="抬眉",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(
            _target(SemanticAction.BROW_HEIGHT, value_range=(0.70, 1.00), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            surprise=0.82, fear=0.42, joy=0.15, anger=-0.35, sadness=-0.25
        ),
        naturalness=0.82,
        priority=58,
        activation_threshold=0.18,
    ),
    ExpressionUnit(
        id="闭眼",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_OPEN, value_range=(0.00, 0.00), jitter=0.00),
        ),
        emotion_correlations=_correlations(
            joy=0.68, sadness=0.49, neutral=0.20, anger=-0.35, surprise=-0.70
        ),
        naturalness=0.86,
        priority=52,
        activation_threshold=0.28,
    ),
    ExpressionUnit(
        id="眯眼",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_OPEN, value_range=(0.10, 0.40), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            joy=0.62, anger=0.48, disgust=0.30, sadness=-0.18, surprise=-0.55
        ),
        naturalness=0.82,
        priority=56,
        activation_threshold=0.15,
    ),
    ExpressionUnit(
        id="睁眼",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_OPEN, value_range=(0.75, 1.00), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            surprise=0.78, fear=0.58, joy=0.20, anger=-0.30, sadness=-0.42
        ),
        naturalness=0.84,
        priority=54,
        activation_threshold=0.18,
    ),
    ExpressionUnit(
        id="眼睛居中",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_X, value_range=(-0.08, 0.08), jitter=0.10),
            _target(SemanticAction.EYE_GAZE_Y, value_range=(-0.08, 0.08), jitter=0.10),
        ),
        emotion_correlations=_correlations(neutral=0.55, joy=0.18),
        naturalness=0.92,
        priority=35,
        activation_threshold=0.20,
    ),
    ExpressionUnit(
        id="眼睛左看",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_X, value_range=(-1.00, -0.70), jitter=0.10),
        ),
        emotion_correlations=_correlations(sadness=0.22, fear=0.18, joy=0.12),
        naturalness=0.82,
        priority=35,
        activation_threshold=0.36,
    ),
    ExpressionUnit(
        id="眼睛右看",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_X, value_range=(0.70, 1.00), jitter=0.10),
        ),
        emotion_correlations=_correlations(sadness=0.22, fear=0.18, joy=0.12),
        naturalness=0.82,
        priority=35,
        activation_threshold=0.36,
    ),
    ExpressionUnit(
        id="眼睛下看",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_Y, value_range=(-1.00, -0.70), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            sadness=0.70, fear=0.25, joy=-0.18, anger=-0.20
        ),
        naturalness=0.84,
        priority=42,
        activation_threshold=0.22,
    ),
    ExpressionUnit(
        id="眼睛上看",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(
            _target(SemanticAction.EYE_GAZE_Y, value_range=(0.70, 1.00), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            anger=0.45, joy=0.20, sadness=-0.20, surprise=0.18
        ),
        naturalness=0.78,
        priority=42,
        activation_threshold=0.24,
    ),
    ExpressionUnit(
        id="嘴角上扬",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.60, 1.00), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            joy=0.96, anger=-0.62, sadness=-0.90, disgust=-0.35, neutral=-0.12
        ),
        naturalness=0.92,
        priority=66,
        activation_threshold=0.10,
    ),
    ExpressionUnit(
        id="嘴角下压",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.00, 0.40), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            sadness=0.92, fear=0.25, joy=-0.92, anger=0.9, neutral=-0.10
        ),
        naturalness=0.88,
        priority=66,
        activation_threshold=0.14,
    ),
    ExpressionUnit(
        id="嘴角平直",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_SMILE, value_range=(0.50, 0.50), jitter=0.10),
        ),
        emotion_correlations=_correlations(neutral=0.55, anger=0.18, sadness=0.16),
        naturalness=0.86,
        priority=34,
        activation_threshold=0.20,
    ),
    ExpressionUnit(
        id="闭嘴",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_OPEN, value_range=(0.00, 0.10), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            anger=0.30, sadness=0.25, neutral=0.24, surprise=-0.62
        ),
        naturalness=0.9,
        priority=45,
        activation_threshold=0.24,
    ),
    ExpressionUnit(
        id="嘴巴微张",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_OPEN, value_range=(0.15, 0.40), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            joy=0.40, surprise=0.58, fear=0.38, sadness=0.16, anger=-0.30
        ),
        naturalness=0.9,
        priority=44,
        activation_threshold=0.18,
    ),
    ExpressionUnit(
        id="嘴巴张大",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_OPEN, value_range=(0.60, 1.00), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            surprise=0.92, fear=0.55, joy=0.25, anger=-0.42, sadness=-0.22
        ),
        naturalness=0.76,
        priority=62,
        activation_threshold=0.20,
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
        emotion_correlations=_correlations(
            anger=0.62, sadness=0.34, disgust=0.42, joy=-0.25, surprise=-0.72
        ),
        naturalness=0.78,
        priority=72,
        activation_threshold=0.16,
    ),
    ExpressionUnit(
        id="嘴部左移",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_X, value_range=(-0.70, -0.25), jitter=0.08),
        ),
        emotion_correlations=_correlations(joy=0.18, anger=0.20, disgust=0.24),
        naturalness=0.82,
        priority=38,
        activation_threshold=0.34,
    ),
    ExpressionUnit(
        id="嘴部右移",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_X, value_range=(0.25, 0.70), jitter=0.08),
        ),
        emotion_correlations=_correlations(joy=0.18, anger=0.20, disgust=0.24),
        naturalness=0.82,
        priority=38,
        activation_threshold=0.34,
    ),
    ExpressionUnit(
        id="嘴部上移",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_Y, value_range=(0.25, 0.70), jitter=0.08),
        ),
        emotion_correlations=_correlations(joy=0.16, surprise=0.18),
        naturalness=0.76,
        priority=35,
        activation_threshold=0.35,
    ),
    ExpressionUnit(
        id="嘴部下移",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(
            _target(SemanticAction.MOUTH_Y, value_range=(-0.70, -0.25), jitter=0.08),
        ),
        emotion_correlations=_correlations(sadness=0.24, fear=0.18),
        naturalness=0.76,
        priority=35,
        activation_threshold=0.35,
    ),
    ExpressionUnit(
        id="抬头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_PITCH, value_range=(0.3, 0.7), jitter=0.1),
        ),
        emotion_correlations=_correlations(
            surprise=0.32, joy=0.18, sadness=-0.30, anger=-0.20
        ),
        naturalness=0.82,
        priority=36,
        activation_threshold=0.30,
    ),
    ExpressionUnit(
        id="低头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_PITCH, value_range=(-0.7, -0.3), jitter=0.10),
        ),
        emotion_correlations=_correlations(
            sadness=0.68, anger=0.42, fear=0.24, joy=-0.18
        ),
        naturalness=0.82,
        priority=44,
        activation_threshold=0.20,
    ),
    ExpressionUnit(
        id="左歪头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_ROLL, value_range=(-0.30, -0.10), jitter=0.10),
        ),
        emotion_correlations=_correlations(joy=0.63, sadness=0.18, fear=0.14),
        naturalness=0.82,
        priority=34,
        activation_threshold=0.24,
    ),
    ExpressionUnit(
        id="右歪头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_ROLL, value_range=(0.10, 0.30), jitter=0.10),
        ),
        emotion_correlations=_correlations(joy=0.63, sadness=0.18, fear=0.14),
        naturalness=0.82,
        priority=34,
        activation_threshold=0.24,
    ),
    ExpressionUnit(
        id="左转头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_YAW, value_range=(-0.75, -0.2), jitter=0.10),
        ),
        emotion_correlations=_correlations(sadness=0.18, fear=0.20, joy=0.12),
        naturalness=0.82,
        priority=32,
        activation_threshold=0.35,
    ),
    ExpressionUnit(
        id="右转头",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(
            _target(SemanticAction.HEAD_YAW, value_range=(0.2, 0.75), jitter=0.10),
        ),
        emotion_correlations=_correlations(sadness=0.18, fear=0.20, joy=0.12),
        naturalness=0.82,
        priority=32,
        activation_threshold=0.35,
    ),
)


BUILTIN_UNITS_BY_ID = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}

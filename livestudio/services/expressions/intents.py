"""内置的组合表情意图模板"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from .models import EmotionKind


@dataclass(frozen=True, slots=True)
class ExpressionIntentOptional:
    """一个可选表情动作项，触发后会整体加入里面的全部 AU"""

    id: str
    units: frozenset[str]
    weight: float


@dataclass(frozen=True, slots=True)
class ExpressionIntentVariant:
    """同一个意图内部由情绪偏移驱动的表现变体"""

    id: str
    emotion: EmotionKind
    direction: Literal["above", "below"] = "above"
    optional_adjustments: Mapping[str, float] = field(default_factory=dict)
    target_offsets: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExpressionIntent:
    """比 AU 更高一层的组合表情意图"""

    id: str
    emotion_profile: Mapping[EmotionKind, float]
    required_units: frozenset[str]
    optional_units: tuple[ExpressionIntentOptional, ...] = ()
    forbidden_units: frozenset[str] = frozenset()
    energy_range: tuple[float, float] = (0.0, 1.0)
    intensity_range: tuple[float, float] = (0.0, 1.0)
    variants: tuple[ExpressionIntentVariant, ...] = ()
    priority: int = 50
    naturalness: float = 1.0


BUILTIN_EXPRESSION_INTENTS: tuple[ExpressionIntent, ...] = (
    ExpressionIntent(
        id="喜悦",
        emotion_profile={
            EmotionKind.JOY: 1.0,
        },
        required_units=frozenset(
            {
                "嘴角上扬",
            },
        ),
        optional_units=(
            ExpressionIntentOptional(
                id="嘴巴微张",
                units=frozenset({"嘴巴微张"}),
                weight=0.6,
            ),
            ExpressionIntentOptional(
                id="眯眼",
                units=frozenset({"眯眼"}),
                weight=0.8,
            ),
            ExpressionIntentOptional(
                id="左歪头",
                units=frozenset({"左歪头"}),
                weight=0.4,
            ),
            ExpressionIntentOptional(
                id="右歪头",
                units=frozenset({"右歪头"}),
                weight=0.4,
            ),
            ExpressionIntentOptional(
                id="轻微抬眉",
                units=frozenset({"轻微抬眉"}),
                weight=0.25,
            ),
            ExpressionIntentOptional(
                id="左转头",
                units=frozenset({"左转头"}),
                weight=0.2,
            ),
            ExpressionIntentOptional(
                id="右转头",
                units=frozenset({"右转头"}),
                weight=0.2,
            ),
        ),
        forbidden_units=frozenset(
            {
                "嘴角下压",
                "抿嘴",
                "眼睛上看",
            },
        ),
        intensity_range=(0.0, 1.0),
        naturalness=0.92,
    ),
    ExpressionIntent(
        id="愤怒",
        emotion_profile={
            EmotionKind.ANGER: 1.0,
        },
        required_units=frozenset(
            {
                "抿嘴",
                "皱眉",
                "眯眼",
            },
        ),
        optional_units=(
            ExpressionIntentOptional(
                id="怒视",
                units=frozenset({"低头", "眼睛上看"}),
                weight=0.5,
            ),
        ),
        forbidden_units=frozenset(
            {
                "嘴角上扬",
                "轻微抬眉",
                "左歪头",
                "右歪头",
            },
        ),
        intensity_range=(0.35, 1.0),
        naturalness=0.82,
    ),
    ExpressionIntent(
        id="悲伤",
        emotion_profile={EmotionKind.SADNESS: 1.0},
        required_units=frozenset(
            {"嘴角下压", "皱眉"},
        ),
        optional_units=(
            ExpressionIntentOptional(
                id="眼睛下看",
                units=frozenset({"眼睛下看"}),
                weight=0.70,
            ),
            ExpressionIntentOptional(
                id="眼睛左看",
                units=frozenset({"眼睛左看"}),
                weight=0.7,
            ),
            ExpressionIntentOptional(
                id="眼睛右看",
                units=frozenset({"眼睛右看"}),
                weight=0.7,
            ),
            ExpressionIntentOptional(
                id="低头",
                units=frozenset({"低头"}),
                weight=0.65,
            ),
        ),
        forbidden_units=frozenset(
            {"嘴角上扬", "眼睛上看"},
        ),
        intensity_range=(0.25, 1.0),
        naturalness=0.88,
    ),
    ExpressionIntent(
        id="阴险笑",
        emotion_profile={EmotionKind.JOY: 0.60, EmotionKind.ANGER: 0.40},
        required_units=frozenset(
            {
                "嘴角上扬",
                "低头",
                "眼睛上看",
            },
        ),
        optional_units=(
            ExpressionIntentOptional(id="眯眼", units=frozenset({"眯眼"}), weight=0.7),
            ExpressionIntentOptional(
                id="左歪头",
                units=frozenset({"左歪头"}),
                weight=0.6,
            ),
            ExpressionIntentOptional(
                id="右歪头",
                units=frozenset({"右歪头"}),
                weight=0.6,
            ),
            ExpressionIntentOptional(
                id="嘴部左移",
                units=frozenset({"嘴部左移"}),
                weight=0.5,
            ),
            ExpressionIntentOptional(
                id="嘴部右移",
                units=frozenset({"嘴部右移"}),
                weight=0.5,
            ),
        ),
        forbidden_units=frozenset(
            {"嘴角下压", "嘴巴微张", "抿嘴", "轻微抬眉"},
        ),
        intensity_range=(0.65, 1.0),
        naturalness=0.78,
    ),
    ExpressionIntent(
        id="苦笑",
        emotion_profile={EmotionKind.JOY: 0.45, EmotionKind.SADNESS: 0.55},
        required_units=frozenset(
            {
                "嘴角上扬",
                "皱眉",
            },
        ),
        optional_units=(
            ExpressionIntentOptional(
                id="嘴巴微张",
                units=frozenset({"嘴巴微张"}),
                weight=0.6,
            ),
            ExpressionIntentOptional(
                id="眼睛下看",
                units=frozenset({"眼睛下看"}),
                weight=0.8,
            ),
            ExpressionIntentOptional(id="低头", units=frozenset({"低头"}), weight=0.6),
            ExpressionIntentOptional(
                id="眼睛左看",
                units=frozenset({"眼睛左看"}),
                weight=0.5,
            ),
            ExpressionIntentOptional(
                id="眼睛右看",
                units=frozenset({"眼睛右看"}),
                weight=0.5,
            ),
        ),
        forbidden_units=frozenset({"眼睛上看"}),
        intensity_range=(0.35, 0.85),
        naturalness=0.84,
    ),
)


BUILTIN_INTENTS_BY_ID = {intent.id: intent for intent in BUILTIN_EXPRESSION_INTENTS}

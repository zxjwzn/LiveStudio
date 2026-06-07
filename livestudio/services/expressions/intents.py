"""内置的组合表情意图模板"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from .models import EmotionKind


@dataclass(frozen=True, slots=True)
class ExpressionIntentVariant:
    """同一个意图内部由情绪偏移驱动的表现变体"""

    id: str
    emotion: EmotionKind
    direction: Literal["above", "below"] = "above"
    optional_unit_adjustments: Mapping[str, float] = field(default_factory=dict)
    target_offsets: Mapping[str, float] = field(default_factory=dict)
    style_tags: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ExpressionIntent:
    """比 AU 更高一层的组合表情意图"""

    id: str
    emotions: Mapping[EmotionKind, float]
    required_units: frozenset[str]
    optional_units: Mapping[str, float] = field(default_factory=dict)
    forbidden_units: frozenset[str] = frozenset()
    output_tags: frozenset[str] = frozenset()
    style_tags: frozenset[str] = frozenset()
    intensity_range: tuple[float, float] = (0.0, 1.0)
    variants: tuple[ExpressionIntentVariant, ...] = ()
    priority: int = 50
    naturalness: float = 1.0


BUILTIN_EXPRESSION_INTENTS: tuple[ExpressionIntent, ...] = (
    ExpressionIntent(
        id="pure_joy",
        emotions={EmotionKind.JOY: 1.0},
        required_units=frozenset({"mouth_smile"}),
        optional_units={"head_tilt": 0.55, "eye_narrow": 0.35, "brow_raise_soft": 0.25},
        forbidden_units=frozenset(
            {"mouth_sinister_smile", "mouth_down", "mouth_press", "gaze_up_white"},
        ),
        output_tags=frozenset({"pure_joy"}),
        style_tags=frozenset({"bright", "friendly"}),
        intensity_range=(0.25, 1.0),
        naturalness=0.92,
    ),
    ExpressionIntent(
        id="anger_tense",
        emotions={EmotionKind.ANGER: 1.0},
        required_units=frozenset({"mouth_press", "brow_knit"}),
        optional_units={"eye_narrow": 0.85, "head_forward": 0.45},
        forbidden_units=frozenset({"mouth_smile", "brow_raise_soft", "head_tilt"}),
        output_tags=frozenset({"anger_tense"}),
        style_tags=frozenset({"tense", "focused"}),
        intensity_range=(0.35, 1.0),
        naturalness=0.82,
    ),
    ExpressionIntent(
        id="sad_downcast",
        emotions={EmotionKind.SADNESS: 1.0},
        required_units=frozenset({"mouth_down"}),
        optional_units={
            "brow_knit": 0.75,
            "gaze_averted_down": 0.65,
            "head_down_averted": 0.55,
        },
        forbidden_units=frozenset(
            {"mouth_smile", "mouth_sinister_smile", "gaze_up_white"},
        ),
        output_tags=frozenset({"sad_downcast"}),
        style_tags=frozenset({"restrained", "pained"}),
        intensity_range=(0.25, 1.0),
        naturalness=0.88,
    ),
    ExpressionIntent(
        id="sinister_smile",
        emotions={EmotionKind.JOY: 0.65, EmotionKind.ANGER: 0.35},
        required_units=frozenset(
            {
                "mouth_sinister_smile",
                "head_down_mischievous",
                "gaze_up_white",
            },
        ),
        optional_units={"eye_narrow": 0.8, "brow_knit": 0.35},
        forbidden_units=frozenset({"mouth_down", "mouth_press", "brow_raise_soft"}),
        output_tags=frozenset({"sinister_smile"}),
        style_tags=frozenset({"sinister", "mischievous", "threatening"}),
        intensity_range=(0.65, 1.0),
        variants=(
            ExpressionIntentVariant(
                id="mischief",
                emotion=EmotionKind.JOY,
                optional_unit_adjustments={"eye_narrow": 0.2},
                target_offsets={"mouth.smile": 0.08, "head.roll": 0.06},
                style_tags=frozenset({"mischief_high"}),
            ),
            ExpressionIntentVariant(
                id="threat",
                emotion=EmotionKind.ANGER,
                optional_unit_adjustments={"brow_knit": 1.2, "eye_narrow": 0.4},
                target_offsets={
                    "eye.gaze.y": 0.18,
                    "eye.open": -0.12,
                    "head.pitch": -0.1,
                },
                style_tags=frozenset({"threat_high"}),
            ),
        ),
        naturalness=0.78,
    ),
    ExpressionIntent(
        id="bitter_smile",
        emotions={EmotionKind.JOY: 0.45, EmotionKind.SADNESS: 0.55},
        required_units=frozenset({"mouth_smile", "brow_knit"}),
        optional_units={"gaze_averted_down": 0.65, "head_down_averted": 0.55},
        forbidden_units=frozenset({"mouth_sinister_smile", "gaze_up_white"}),
        output_tags=frozenset({"bitter_smile"}),
        style_tags=frozenset({"restrained", "pained", "soft"}),
        intensity_range=(0.35, 0.85),
        naturalness=0.84,
    ),
    ExpressionIntent(
        id="wronged",
        emotions={EmotionKind.SADNESS: 1.0},
        required_units=frozenset({"brow_raise_soft", "mouth_down"}),
        optional_units={"gaze_averted_down": 0.85, "head_down_averted": 0.65},
        forbidden_units=frozenset(
            {"mouth_sinister_smile", "gaze_up_white", "eye_narrow"},
        ),
        output_tags=frozenset({"wronged"}),
        style_tags=frozenset({"vulnerable", "restrained", "soft"}),
        intensity_range=(0.45, 0.9),
        naturalness=0.88,
    ),
)


BUILTIN_INTENTS_BY_ID = {intent.id: intent for intent in BUILTIN_EXPRESSION_INTENTS}

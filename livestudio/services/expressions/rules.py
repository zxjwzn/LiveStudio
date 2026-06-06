"""内置的表情组合兼容规则"""

from __future__ import annotations

import math

from .models import EmotionKind, ExpressionCombinationRule

BUILTIN_COMBINATION_RULES: tuple[ExpressionCombinationRule, ...] = (
    ExpressionCombinationRule(
        id="anger_blocks_friendly_brightness",
        emotions=frozenset({EmotionKind.ANGER}),
        forbid_tags=frozenset({"friendly", "bright"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="sadness_blocks_bright_smiles",
        emotions=frozenset({EmotionKind.SADNESS}),
        forbid_tags=frozenset({"bright", "smile"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="joy_blocks_downcast_tension",
        emotions=frozenset({EmotionKind.JOY}),
        forbid_tags=frozenset({"mouth_down", "pained", "pressed"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="narrow_and_wide_eyes_are_incompatible",
        require_tags=frozenset({"eye_narrow", "wide"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="brow_raise_and_brow_knit_are_incompatible",
        require_tags=frozenset({"brow_raise", "brow_knit"}),
        penalty=math.inf,
    ),
)

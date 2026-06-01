"""Built-in expression combination compatibility rules."""

from __future__ import annotations

import math

from .models import EmotionKind, ExpressionCombinationRule

BUILTIN_COMBINATION_RULES: tuple[ExpressionCombinationRule, ...] = (
    ExpressionCombinationRule(
        id="anger_blocks_friendly_smiles",
        emotions=frozenset({EmotionKind.ANGER}),
        forbid_tags=frozenset({"friendly", "bright"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="sadness_blocks_bright_mouth",
        emotions=frozenset({EmotionKind.SADNESS}),
        forbid_tags=frozenset({"bright"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="joy_penalizes_tense_suspicion",
        emotions=frozenset({EmotionKind.JOY}),
        require_tags=frozenset({"tense", "suspicious"}),
        penalty=0.9,
    ),
)

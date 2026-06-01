"""Emotion-driven expression synthesis service."""

from .models import (
    EmotionKind,
    EmotionRequest,
    ExpressionCombinationRule,
    ExpressionRegion,
    ExpressionSignature,
    ExpressionUnit,
    ScoredExpressionUnit,
    SelectedExpression,
)
from .rules import BUILTIN_COMBINATION_RULES
from .selector import ExpressionSelector
from .service import ExpressionService
from .units import BUILTIN_EXPRESSION_UNITS, BUILTIN_UNITS_BY_ID

__all__ = [
    "BUILTIN_COMBINATION_RULES",
    "BUILTIN_EXPRESSION_UNITS",
    "BUILTIN_UNITS_BY_ID",
    "EmotionKind",
    "EmotionRequest",
    "ExpressionCombinationRule",
    "ExpressionRegion",
    "ExpressionSelector",
    "ExpressionService",
    "ExpressionSignature",
    "ExpressionUnit",
    "ScoredExpressionUnit",
    "SelectedExpression",
]

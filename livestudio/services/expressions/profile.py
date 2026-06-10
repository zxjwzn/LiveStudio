"""模型级 AU 表情配置的默认值"""

from __future__ import annotations

from .models import ExpressionProfileConfig, ExpressionRuleConfig, ExpressionUnitConfig
from .rules import BUILTIN_COMBINATION_RULES
from .units import BUILTIN_EXPRESSION_UNITS


def default_expression_profile() -> ExpressionProfileConfig:
    """返回会写入模型配置的默认 AU、规则和运行时参数"""

    return ExpressionProfileConfig(
        units={
            unit.id: ExpressionUnitConfig.from_unit(unit)
            for unit in BUILTIN_EXPRESSION_UNITS
        },
        rules=[
            ExpressionRuleConfig.from_rule(rule) for rule in BUILTIN_COMBINATION_RULES
        ],
    )

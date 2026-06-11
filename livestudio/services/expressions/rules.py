"""内置的表情组合兼容规则"""

from __future__ import annotations

import math

from .models import ExpressionCombinationRule

BUILTIN_COMBINATION_RULES: tuple[ExpressionCombinationRule, ...] = (
    ExpressionCombinationRule(
        id="眉毛",
        any_of_unit_ids=frozenset({"皱眉", "轻微抬眉", "抬眉"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="眼睛",
        any_of_unit_ids=frozenset({"闭眼", "眯眼", "睁眼"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="水平视线",
        any_of_unit_ids=frozenset({"眼睛居中", "眼睛左看", "眼睛右看"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="垂直视线",
        any_of_unit_ids=frozenset({"眼睛居中", "眼睛下看", "眼睛上看"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="嘴角",
        any_of_unit_ids=frozenset({"嘴角上扬", "嘴角下压", "嘴角平直"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="嘴部开合",
        any_of_unit_ids=frozenset({"闭嘴", "嘴巴微张", "嘴巴张大"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="嘴部横向位移",
        any_of_unit_ids=frozenset({"嘴部左移", "嘴部右移"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="嘴部纵向位移",
        any_of_unit_ids=frozenset({"嘴部上移", "嘴部下移"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="头部俯仰",
        any_of_unit_ids=frozenset({"抬头", "低头"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="头部侧歪",
        any_of_unit_ids=frozenset({"左歪头", "右歪头"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="头部转向",
        any_of_unit_ids=frozenset({"左转头", "右转头"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="抿嘴削弱嘴角上扬",
        required_unit_ids=frozenset({"抿嘴", "嘴角上扬"}),
        penalty=0.18,
    ),
    ExpressionCombinationRule(
        id="抿嘴削弱嘴角下压",
        required_unit_ids=frozenset({"抿嘴", "嘴角下压"}),
        penalty=0.12,
    ),
    ExpressionCombinationRule(
        id="低头强化眼睛上看",
        required_unit_ids=frozenset({"低头", "眼睛上看"}),
        bonus=0.18,
    ),
    ExpressionCombinationRule(
        id="眯眼强化眼睛上看",
        required_unit_ids=frozenset({"眯眼", "眼睛上看"}),
        bonus=0.10,
    ),
    ExpressionCombinationRule(
        id="眯眼强化嘴角上扬",
        required_unit_ids=frozenset({"眯眼", "嘴角上扬"}),
        bonus=0.08,
    ),
)

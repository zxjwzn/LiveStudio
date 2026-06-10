"""内置的 AU 组合兼容规则"""

from __future__ import annotations

import math

from .models import EmotionKind, ExpressionCombinationRule, ExpressionRuleKind

BUILTIN_COMBINATION_RULES: tuple[ExpressionCombinationRule, ...] = (
    ExpressionCombinationRule(
        id="眉毛互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"皱眉", "轻微抬眉", "抬眉"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="眼睛开合互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"闭眼", "眯眼", "睁眼"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="水平视线互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"眼睛居中", "眼睛左看", "眼睛右看"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="垂直视线互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"眼睛居中", "眼睛下看", "眼睛上看"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="嘴角互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"嘴角上扬", "嘴角下压", "嘴角平直"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="嘴部开合互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"闭嘴", "嘴巴微张", "嘴巴张大"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="嘴部横向位移互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"嘴部左移", "嘴部右移"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="嘴部纵向位移互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"嘴部上移", "嘴部下移"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="头部俯仰互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"抬头", "低头"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="头部侧歪互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"左歪头", "右歪头"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="头部转向互斥",
        kind=ExpressionRuleKind.MUTEX,
        unit_ids=frozenset({"左转头", "右转头"}),
        penalty=math.inf,
    ),
    ExpressionCombinationRule(
        id="喜悦笑眼增强",
        kind=ExpressionRuleKind.SYNERGY,
        emotions=frozenset({EmotionKind.JOY}),
        unit_ids=frozenset({"嘴角上扬", "眯眼"}),
        bonus=0.10,
    ),
    ExpressionCombinationRule(
        id="怒视增强",
        kind=ExpressionRuleKind.SYNERGY,
        emotions=frozenset({EmotionKind.ANGER}),
        unit_ids=frozenset({"皱眉", "眯眼"}),
        bonus=0.22,
    ),
    ExpressionCombinationRule(
        id="低头上目线增强",
        kind=ExpressionRuleKind.SYNERGY,
        emotions=frozenset({EmotionKind.ANGER}),
        unit_ids=frozenset({"低头", "眼睛上看"}),
        bonus=0.3,
    ),
    ExpressionCombinationRule(
        id="悲伤低头增强",
        kind=ExpressionRuleKind.SYNERGY,
        emotions=frozenset({EmotionKind.SADNESS}),
        unit_ids=frozenset({"嘴角下压", "眼睛下看", "低头"}),
        bonus=0.18,
    ),
    ExpressionCombinationRule(
        id="抿嘴削弱嘴角上扬",
        kind=ExpressionRuleKind.SUPPRESSION,
        source_unit_id="抿嘴",
        target_unit_id="嘴角上扬",
        strength=0.35,
    ),
    ExpressionCombinationRule(
        id="怒视依赖",
        kind=ExpressionRuleKind.DEPENDENCY,
        source_unit_id="眼睛上看",
        target_unit_id="低头",
        emotions=frozenset({EmotionKind.ANGER}),
        penalty=math.inf,
    ),
)

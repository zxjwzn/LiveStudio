"""内置默认表情 AU 与规则

仅在首次初始化模型配置文件时作为种子写入（见 PlatformModelConfig.init_defaults）。
配置文件一旦存在，加载时完全以文件内容为准，不再引用这里的默认值。

只放纯语义 AU（基于平台无关的 SemanticAction），不含任何平台特定的原生表情；
原生表情绑定具体模型的 .exp3.json，应由各模型自行配置。

每个 AU 自带 id，以列表返回，可直接序列化进配置文件。
"""

from __future__ import annotations

from livestudio.services.expression.models import (
    BonusRule,
    EmotionKind,
    ExpressionRule,
    ExpressionTarget,
    MutualExclusionRule,
    SemanticAction,
    SemanticExpressionUnit,
)


def default_semantic_units() -> list[SemanticExpressionUnit]:
    """返回通用默认语义 AU（每次调用新建实例），id 写入对象"""

    return [
        # —— 喜悦 ——
        SemanticExpressionUnit(
            id="嘴角上扬",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.MOUTH_SMILE, min_value=0.55, max_value=0.90
                )
            ],
            emotions={EmotionKind.JOY: 0.95, EmotionKind.SURPRISE: 0.30},
        ),
        SemanticExpressionUnit(
            id="咧嘴笑",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.MOUTH_SMILE, min_value=0.80, max_value=1.00
                )
            ],
            emotions={EmotionKind.JOY: 0.80},
            activation_threshold=0.30,
        ),
        SemanticExpressionUnit(
            id="眯眼笑",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.EYE_OPEN, min_value=0.35, max_value=0.55
                )
            ],
            emotions={EmotionKind.JOY: 0.70},
        ),
        # —— 悲伤 ——
        SemanticExpressionUnit(
            id="垂眉",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.BROW_HEIGHT, min_value=0.00, max_value=0.20
                )
            ],
            emotions={EmotionKind.SADNESS: 0.85, EmotionKind.ANGER: 0.40},
        ),
        SemanticExpressionUnit(
            id="抿嘴",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.MOUTH_SMILE, min_value=0.00, max_value=0.15
                )
            ],
            emotions={EmotionKind.SADNESS: 0.70, EmotionKind.ANGER: 0.35},
        ),
        SemanticExpressionUnit(
            id="低头",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.HEAD_PITCH, min_value=-0.45, max_value=-0.20
                )
            ],
            emotions={EmotionKind.SADNESS: 0.75},
        ),
        SemanticExpressionUnit(
            id="半垂眼",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.EYE_OPEN, min_value=0.30, max_value=0.50
                )
            ],
            emotions={EmotionKind.SADNESS: 0.55},
        ),
        # —— 愤怒 ——
        SemanticExpressionUnit(
            id="皱眉",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.BROW_HEIGHT, min_value=0.00, max_value=0.15
                )
            ],
            emotions={EmotionKind.ANGER: 0.90, EmotionKind.SADNESS: 0.45},
            activation_threshold=0.10,
        ),
        SemanticExpressionUnit(
            id="瞪眼",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.EYE_OPEN, min_value=0.85, max_value=1.00
                )
            ],
            emotions={EmotionKind.ANGER: 0.80, EmotionKind.SURPRISE: 0.60},
        ),
        SemanticExpressionUnit(
            id="抿紧嘴",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.MOUTH_OPEN, min_value=0.00, max_value=0.05
                )
            ],
            emotions={EmotionKind.ANGER: 0.55},
        ),
        # —— 惊讶 ——
        SemanticExpressionUnit(
            id="挑眉",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.BROW_HEIGHT, min_value=0.60, max_value=0.85
                )
            ],
            emotions={EmotionKind.SURPRISE: 0.85, EmotionKind.JOY: 0.45},
        ),
        SemanticExpressionUnit(
            id="瞪大眼",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.EYE_OPEN, min_value=0.90, max_value=1.00
                )
            ],
            emotions={EmotionKind.SURPRISE: 0.95, EmotionKind.FEAR: 0.55},
        ),
        SemanticExpressionUnit(
            id="张嘴",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.MOUTH_OPEN, min_value=0.40, max_value=0.70
                )
            ],
            emotions={EmotionKind.SURPRISE: 0.80, EmotionKind.FEAR: 0.40},
        ),
        # —— 恐惧 ——
        SemanticExpressionUnit(
            id="缩头",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.HEAD_PITCH, min_value=-0.40, max_value=-0.15
                )
            ],
            emotions={EmotionKind.FEAR: 0.70, EmotionKind.SADNESS: 0.30},
        ),
        # —— 厌恶 ——
        SemanticExpressionUnit(
            id="歪嘴",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.MOUTH_X, min_value=0.30, max_value=0.60
                )
            ],
            emotions={EmotionKind.DISGUST: 0.85},
        ),
        SemanticExpressionUnit(
            id="蹙眉",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.BROW_HEIGHT, min_value=0.05, max_value=0.25
                )
            ],
            emotions={EmotionKind.DISGUST: 0.70, EmotionKind.ANGER: 0.35},
        ),
        # —— 中性 ——
        SemanticExpressionUnit(
            id="平视",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.EYE_OPEN, min_value=0.70, max_value=0.85
                )
            ],
            emotions={EmotionKind.NEUTRAL: 0.80},
        ),
        SemanticExpressionUnit(
            id="自然眉",
            targets=[
                ExpressionTarget(
                    action=SemanticAction.BROW_HEIGHT, min_value=0.40, max_value=0.55
                )
            ],
            emotions={EmotionKind.NEUTRAL: 0.70},
        ),
    ]


def default_rules() -> list[ExpressionRule]:
    """返回通用默认规则（互斥 + 情绪联动加分）"""

    return [
        MutualExclusionRule(
            id="眉毛互斥",
            unit_ids=frozenset({"挑眉", "皱眉", "垂眉", "蹙眉", "自然眉"}),
        ),
        MutualExclusionRule(
            id="眼睛互斥",
            unit_ids=frozenset({"眯眼笑", "半垂眼", "瞪眼", "瞪大眼", "平视"}),
        ),
        BonusRule(
            id="笑眼联动",
            unit_ids=frozenset({"嘴角上扬", "眯眼笑"}),
            value=0.25,
            emotions=frozenset({EmotionKind.JOY}),
        ),
        BonusRule(
            id="怒目联动",
            unit_ids=frozenset({"皱眉", "瞪眼"}),
            value=0.22,
            emotions=frozenset({EmotionKind.ANGER}),
        ),
        BonusRule(
            id="悲伤联动",
            unit_ids=frozenset({"垂眉", "低头"}),
            value=0.20,
            emotions=frozenset({EmotionKind.SADNESS}),
        ),
        BonusRule(
            id="惊讶联动",
            unit_ids=frozenset({"瞪大眼", "张嘴"}),
            value=0.25,
            emotions=frozenset({EmotionKind.SURPRISE}),
        ),
    ]

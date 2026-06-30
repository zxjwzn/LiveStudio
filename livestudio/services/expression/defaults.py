"""内置默认表情 AU 与规则

仅在首次初始化模型配置文件时作为种子写入（见 PlatformModelConfig.init_defaults）。
配置文件一旦存在，加载时完全以文件内容为准，不再引用这里的默认值。

只放纯语义 AU（基于平台无关的 SemanticAction），不含任何平台特定的原生表情；
原生表情绑定具体模型的 .exp3.json，应由各模型自行配置。

每个 AU 自带 id，以列表返回，可直接序列化进配置文件。
"""

from __future__ import annotations

from livestudio.services.expression.models import (
    BindingRule,
    BonusRule,
    EmotionKind,
    ExpressionRule,
    ExpressionTarget,
    MutualExclusionRule,
    PenaltyRule,
    SemanticAction,
    SemanticExpressionUnit,
)


def default_semantic_units() -> list[SemanticExpressionUnit]:
    """返回通用默认语义 AU（每次调用新建实例），id 写入对象"""

    return [
        # —— 眉毛 ——
        SemanticExpressionUnit(
            id="皱眉",
            targets=[ExpressionTarget(action=SemanticAction.BROW_HEIGHT, min_value=0.00, max_value=0.10)],
            emotions={EmotionKind.ANGER: 0.92, EmotionKind.SADNESS: 0.42, EmotionKind.FEAR: 0.35},
        ),
        SemanticExpressionUnit(
            id="轻微抬眉",
            targets=[ExpressionTarget(action=SemanticAction.BROW_HEIGHT, min_value=0.50, max_value=0.70)],
            emotions={EmotionKind.JOY: 0.28, EmotionKind.SURPRISE: 0.45, EmotionKind.FEAR: 0.20},
        ),
        SemanticExpressionUnit(
            id="抬眉",
            targets=[ExpressionTarget(action=SemanticAction.BROW_HEIGHT, min_value=0.70, max_value=1.00)],
            emotions={EmotionKind.SURPRISE: 0.82, EmotionKind.FEAR: 0.42, EmotionKind.JOY: 0.15},
        ),
        # —— 眼睛开合 ——
        SemanticExpressionUnit(
            id="闭眼",
            targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.00, max_value=0.00)],
            emotions={EmotionKind.JOY: 0.36, EmotionKind.SADNESS: 0.49},
        ),
        SemanticExpressionUnit(
            id="眯眼",
            targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.20, max_value=0.40)],
            emotions={EmotionKind.JOY: 0.76, EmotionKind.ANGER: 0.72, EmotionKind.DISGUST: 0.30},
        ),
        SemanticExpressionUnit(
            id="睁眼",
            targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.75, max_value=1.00)],
            emotions={EmotionKind.SURPRISE: 0.78, EmotionKind.FEAR: 0.58, EmotionKind.JOY: 0.20},
        ),
        SemanticExpressionUnit(
            id="wink 左眼",
            targets=[
                ExpressionTarget(action=SemanticAction.EYE_OPEN_LEFT, min_value=0.00, max_value=0.00),
                ExpressionTarget(action=SemanticAction.EYE_OPEN_RIGHT, min_value=0.75, max_value=1.00),
            ],
            emotions={EmotionKind.JOY: 0.58},
        ),
        SemanticExpressionUnit(
            id="wink 右眼",
            targets=[
                ExpressionTarget(action=SemanticAction.EYE_OPEN_LEFT, min_value=0.75, max_value=1.00),
                ExpressionTarget(action=SemanticAction.EYE_OPEN_RIGHT, min_value=0.00, max_value=0.00),
            ],
            emotions={EmotionKind.JOY: 0.58},
        ),
        # —— 视线方向 ——
        SemanticExpressionUnit(
            id="眼睛居中",
            targets=[
                ExpressionTarget(action=SemanticAction.EYE_GAZE_X, min_value=-0.08, max_value=0.08),
                ExpressionTarget(action=SemanticAction.EYE_GAZE_Y, min_value=-0.08, max_value=0.08),
            ],
            emotions={EmotionKind.JOY: 0.18},
        ),
        SemanticExpressionUnit(
            id="眼睛左看",
            targets=[ExpressionTarget(action=SemanticAction.EYE_GAZE_X, min_value=-1.00, max_value=-0.70)],
            emotions={EmotionKind.SADNESS: 0.22, EmotionKind.FEAR: 0.18, EmotionKind.JOY: 0.12},
        ),
        SemanticExpressionUnit(
            id="眼睛右看",
            targets=[ExpressionTarget(action=SemanticAction.EYE_GAZE_X, min_value=0.70, max_value=1.00)],
            emotions={EmotionKind.SADNESS: 0.22, EmotionKind.FEAR: 0.18, EmotionKind.JOY: 0.12},
        ),
        SemanticExpressionUnit(
            id="眼睛下看",
            targets=[ExpressionTarget(action=SemanticAction.EYE_GAZE_Y, min_value=-1.00, max_value=-0.70)],
            emotions={EmotionKind.SADNESS: 0.70, EmotionKind.FEAR: 0.25},
        ),
        SemanticExpressionUnit(
            id="眼睛上看",
            targets=[ExpressionTarget(action=SemanticAction.EYE_GAZE_Y, min_value=0.70, max_value=1.00)],
            emotions={EmotionKind.ANGER: 0.45, EmotionKind.JOY: 0.20, EmotionKind.SURPRISE: 0.18},
        ),
        # —— 嘴角 ——
        SemanticExpressionUnit(
            id="嘴角上扬",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.60, max_value=1.00)],
            emotions={EmotionKind.JOY: 0.82},
        ),
        SemanticExpressionUnit(
            id="嘴角下压",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.00, max_value=0.40)],
            emotions={EmotionKind.SADNESS: 0.92, EmotionKind.FEAR: 0.25, EmotionKind.ANGER: 0.44},
        ),
        SemanticExpressionUnit(
            id="嘴角平直",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.50, max_value=0.50)],
            emotions={EmotionKind.ANGER: 0.18, EmotionKind.SADNESS: 0.16},
        ),
        # —— 嘴部开合 ——
        SemanticExpressionUnit(
            id="闭嘴",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_OPEN, min_value=0.00, max_value=0.10)],
            emotions={EmotionKind.ANGER: 0.30, EmotionKind.SADNESS: 0.25},
        ),
        SemanticExpressionUnit(
            id="嘴巴微张",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_OPEN, min_value=0.15, max_value=0.20)],
            emotions={
                EmotionKind.JOY: 0.76,
                EmotionKind.SURPRISE: 0.58,
                EmotionKind.FEAR: 0.88,
                EmotionKind.SADNESS: 0.16,
            },
        ),
        SemanticExpressionUnit(
            id="嘴巴张大",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_OPEN, min_value=0.60, max_value=1.00)],
            emotions={EmotionKind.SURPRISE: 0.92, EmotionKind.FEAR: 0.79, EmotionKind.JOY: 0.25},
        ),
        # —— 嘴部位移 ——
        SemanticExpressionUnit(
            id="嘴部左移",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_X, min_value=-0.70, max_value=-0.25)],
            emotions={EmotionKind.JOY: 0.18, EmotionKind.ANGER: 0.50, EmotionKind.DISGUST: 0.24},
        ),
        SemanticExpressionUnit(
            id="嘴部右移",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_X, min_value=0.25, max_value=0.70)],
            emotions={EmotionKind.JOY: 0.18, EmotionKind.ANGER: 0.50, EmotionKind.DISGUST: 0.24},
        ),
        SemanticExpressionUnit(
            id="嘴部上移",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_Y, min_value=0.25, max_value=0.70)],
            emotions={EmotionKind.JOY: 0.16, EmotionKind.SURPRISE: 0.18},
        ),
        SemanticExpressionUnit(
            id="嘴部下移",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_Y, min_value=-0.70, max_value=-0.25)],
            emotions={EmotionKind.SADNESS: 0.24, EmotionKind.FEAR: 0.18},
        ),
        SemanticExpressionUnit(
            id="嘴部居中",
            targets=[
                ExpressionTarget(action=SemanticAction.MOUTH_Y, min_value=0, max_value=0),
                ExpressionTarget(action=SemanticAction.MOUTH_X, min_value=0, max_value=0),
            ],
            emotions={EmotionKind.SADNESS: 0.24, EmotionKind.FEAR: 0.18},
        ),
        # —— 头部俯仰 ——
        SemanticExpressionUnit(
            id="抬头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_PITCH, min_value=0.3, max_value=0.7)],
            emotions={EmotionKind.SURPRISE: 0.32, EmotionKind.JOY: 0.10},
        ),
        SemanticExpressionUnit(
            id="低头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_PITCH, min_value=-0.7, max_value=-0.3)],
            emotions={EmotionKind.SADNESS: 0.68, EmotionKind.ANGER: 0.42, EmotionKind.FEAR: 0.24},
        ),
        # —— 头部侧歪 ——
        SemanticExpressionUnit(
            id="左歪头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_ROLL, min_value=-0.30, max_value=-0.10)],
            emotions={EmotionKind.JOY: 0.45, EmotionKind.SADNESS: 0.18, EmotionKind.FEAR: 0.14},
        ),
        SemanticExpressionUnit(
            id="右歪头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_ROLL, min_value=0.10, max_value=0.30)],
            emotions={EmotionKind.JOY: 0.45, EmotionKind.SADNESS: 0.18, EmotionKind.FEAR: 0.14},
        ),
        # —— 头部转向 ——
        SemanticExpressionUnit(
            id="左转头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_YAW, min_value=-0.75, max_value=-0.2)],
            emotions={EmotionKind.SADNESS: 0.18, EmotionKind.FEAR: 0.20, EmotionKind.JOY: 0.12},
        ),
        SemanticExpressionUnit(
            id="右转头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_YAW, min_value=0.2, max_value=0.75)],
            emotions={EmotionKind.SADNESS: 0.18, EmotionKind.FEAR: 0.20, EmotionKind.JOY: 0.12},
        ),
    ]


def default_rules() -> list[ExpressionRule]:
    """返回通用默认规则（互斥 + 情绪联动加分 + 抑制 + 强制依赖）"""

    return [
        # —— 情绪联动加分（SYNERGY）——
        BonusRule(
            id="喜悦笑眼增强",
            unit_ids=frozenset({"嘴角上扬", "眯眼"}),
            value=0.18,
            emotions=frozenset({EmotionKind.JOY}),
        ),
        BonusRule(
            id="怒视增强",
            unit_ids=frozenset({"皱眉", "眯眼"}),
            value=0.22,
            emotions=frozenset({EmotionKind.ANGER}),
        ),
        BonusRule(
            id="怒眉嘴角增强",
            unit_ids=frozenset({"嘴角下压", "皱眉"}),
            value=0.5,
            emotions=frozenset({EmotionKind.ANGER}),
        ),
        BonusRule(
            id="低头上目线增强",
            unit_ids=frozenset({"低头", "眼睛上看"}),
            value=0.3,
            emotions=frozenset({EmotionKind.ANGER}),
        ),
        BonusRule(
            id="悲伤低头增强",
            unit_ids=frozenset({"嘴角下压", "眼睛下看", "低头"}),
            value=0.18,
            emotions=frozenset({EmotionKind.SADNESS}),
        ),
        # —— 抑制（SUPPRESSION）——
        PenaltyRule(
            id="抿嘴削弱嘴角上扬",
            unit_ids=frozenset({"抿嘴", "嘴角上扬"}),
            value=0.35,
        ),
        # —— 互斥（MUTEX）——
        MutualExclusionRule(
            id="wink 左右互斥",
            unit_ids=frozenset({"wink 左眼", "wink 右眼"}),
        ),
        # —— 强制依赖（DEPENDENCY）——
        BindingRule(
            id="怒视依赖",
            unit_ids=frozenset({"眼睛上看", "低头"}),
            emotions=frozenset({EmotionKind.ANGER}),
        ),
    ]

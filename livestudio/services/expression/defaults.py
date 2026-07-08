"""内置默认表情 AU 与规则

仅在首次初始化模型配置文件时作为种子写入（见 PlatformModelConfig.init_defaults）。
配置文件一旦存在，加载时完全以文件内容为准，不再引用这里的默认值。

只放纯语义 AU（基于平台无关的 SemanticAction），不含任何平台特定的原生表情；
原生表情绑定具体模型的 .exp3.json，应由各模型自行配置。

每个 AU 自带 id，以列表返回，可直接序列化进配置文件。

v3 变化：
- EmotionKind 扩充至 7 列（基础 3 + 演出 4），默认 AU 补齐新列打分。
- 姿态/调味 AU（歪头/转头/抬头）改用 baseline 百搭分，不再到处补零碎小分。
- 新增复合 AU「阴险抬眼」（低头 + 抬眼的合取），替代旧 BindingRule「怒视依赖」。
- 规则收缩：物理互斥已由 action 隐式冲突覆盖，身份错位由典型度门压制，
  合取语义改由复合 AU 表达——默认规则为空，仅留作模型级例外通道。
"""

from __future__ import annotations

from livestudio.services.expression.models import (
    EmotionKind,
    ExpressionRule,
    ExpressionTarget,
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
            emotions={
                EmotionKind.ANGER: 0.85,
                EmotionKind.SADNESS: 0.89,
                EmotionKind.WRY: 0.58,
            },
        ),
        SemanticExpressionUnit(
            id="轻微抬眉",
            targets=[ExpressionTarget(action=SemanticAction.BROW_HEIGHT, min_value=0.50, max_value=0.70)],
            emotions={EmotionKind.JOY: 0.58, EmotionKind.SMUG: 0.50},
        ),
        SemanticExpressionUnit(
            id="抬眉",
            targets=[ExpressionTarget(action=SemanticAction.BROW_HEIGHT, min_value=0.70, max_value=1.00)],
            emotions={EmotionKind.JOY: 0.69, EmotionKind.SURPRISE: 0.89},
        ),
        # —— 眼睛开合 ——
        SemanticExpressionUnit(
            id="闭眼",
            targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.00, max_value=0.00)],
            emotions={
                EmotionKind.SADNESS: 0.23,
                EmotionKind.WRY: 0.34,
                EmotionKind.SHY: 0.30,
            },
        ),
        SemanticExpressionUnit(
            id="眯眼",
            targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.20, max_value=0.40)],
            emotions={
                EmotionKind.JOY: 0.76,
                EmotionKind.ANGER: 0.88,
                EmotionKind.SADNESS: 0.79,
                EmotionKind.SMUG: 0.70,
            },
        ),
        SemanticExpressionUnit(
            id="睁眼",
            targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.75, max_value=1.00)],
            emotions={EmotionKind.JOY: 0.20, EmotionKind.SURPRISE: 0.99},
        ),
        SemanticExpressionUnit(
            id="瞪眼",
            targets=[ExpressionTarget(action=SemanticAction.EYE_WIDE, min_value=0.50, max_value=1.00)],
            emotions={EmotionKind.SURPRISE: 0.99, EmotionKind.ANGER: 0.40},
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
            id="目移",
            targets=[ExpressionTarget(action=SemanticAction.EYE_GAZE_X, min_value=-1.00, max_value=1)],
            emotions={
                EmotionKind.SADNESS: 0.72,
                EmotionKind.SHY: 0.70,
            },
        ),
        SemanticExpressionUnit(
            id="眼睛下看",
            targets=[ExpressionTarget(action=SemanticAction.EYE_GAZE_Y, min_value=-1.00, max_value=-0.70)],
            emotions={
                EmotionKind.SADNESS: 0.80,
                EmotionKind.WRY: 0.80,
                EmotionKind.SHY: 0.40,
            },
        ),
        SemanticExpressionUnit(
            id="眼睛上看",
            targets=[ExpressionTarget(action=SemanticAction.EYE_GAZE_Y, min_value=0.70, max_value=1.00)],
            emotions={EmotionKind.WRY: 0.80},
        ),
        # —— 嘴角 ——
        SemanticExpressionUnit(
            id="嘴角上扬",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.60, max_value=1.00)],
            emotions={
                EmotionKind.JOY: 0.82,
                EmotionKind.SMUG: 0.65,
                EmotionKind.WRY: 0.60,
                EmotionKind.SHY: 0.45,
            },
        ),
        SemanticExpressionUnit(
            id="嘴角下撇",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.00, max_value=0.40)],
            emotions={EmotionKind.SADNESS: 0.92, EmotionKind.ANGER: 0.44, EmotionKind.SMUG: 0.45, EmotionKind.SURPRISE: 0.99},
        ),
        # —— 嘴部开合 ——
        SemanticExpressionUnit(
            id="闭嘴",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_OPEN, min_value=0.00, max_value=0.10)],
            emotions={
                EmotionKind.ANGER: 0.30,
                EmotionKind.SADNESS: 0.25,
                EmotionKind.SURPRISE: 0.7,
            },
        ),
        SemanticExpressionUnit(
            id="嘴巴微张",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_OPEN, min_value=0.15, max_value=0.20)],
            emotions={
                EmotionKind.JOY: 0.76,
                EmotionKind.SADNESS: 0.16,
                EmotionKind.SURPRISE: 0.60,
                EmotionKind.SMUG: 0.30,
            },
        ),
        SemanticExpressionUnit(
            id="嘴巴张大",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_OPEN, min_value=0.60, max_value=1.00)],
            emotions={EmotionKind.JOY: 0.25, EmotionKind.SURPRISE: 0.70},
        ),
        SemanticExpressionUnit(
            id="下颌张开",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_JAW_OPEN, min_value=0.50, max_value=1.00)],
            emotions={EmotionKind.SURPRISE: 0.75, EmotionKind.JOY: 0.30},
        ),
        SemanticExpressionUnit(
            id="抿嘴",
            targets=[
                ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.40, max_value=0.40),
                ExpressionTarget(action=SemanticAction.MOUTH_OPEN, min_value=0.0, max_value=0.00),
            ],
            emotions={
                EmotionKind.ANGER: 0.86,
                EmotionKind.SADNESS: 0.34,
            },
        ),
        # —— 唇形 ——（funnel / pucker± / shrug：与嘴角、嘴部开合各占独立 action，可叠加）
        SemanticExpressionUnit(
            id="拢嘴",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_FUNNEL, min_value=0.50, max_value=1.00)],
            emotions={EmotionKind.SMUG: 0.40},
        ),
        SemanticExpressionUnit(
            id="撅嘴",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_PUCKER, min_value=0.40, max_value=1.00)],
            emotions={EmotionKind.SHY: 0.55, EmotionKind.SADNESS: 0.30, EmotionKind.WRY: 0.30},
        ),
        SemanticExpressionUnit(
            id="咧嘴",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_PUCKER, min_value=-1.00, max_value=-0.40)],
            emotions={EmotionKind.JOY: 0.40, EmotionKind.SMUG: 0.35, EmotionKind.WRY: 0.30},
        ),
        SemanticExpressionUnit(
            id="耸嘴",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_SHRUG, min_value=0.40, max_value=1.00)],
            emotions={
                EmotionKind.WRY: 0.62,
                EmotionKind.ANGER: 0.35,
                EmotionKind.SADNESS: 0.28,
                EmotionKind.SMUG: 0.30,
            },
        ),
        # —— 颊 / 舌 ——
        SemanticExpressionUnit(
            id="鼓腮",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_CHEEK_PUFF, min_value=0.50, max_value=1.00)],
            emotions={EmotionKind.SHY: 0.40, EmotionKind.ANGER: 0.89},
        ),
        SemanticExpressionUnit(
            id="微微吐舌",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_TONGUE_OUT, min_value=0.30, max_value=0.60)],
            emotions={EmotionKind.SMUG: 0.45, EmotionKind.JOY: 0.35, EmotionKind.SHY: 0.25},
        ),
        # —— 嘴部位移 ——
        SemanticExpressionUnit(
            id="嘴移",
            targets=[ExpressionTarget(action=SemanticAction.MOUTH_X, min_value=-1, max_value=1)],
            emotions={EmotionKind.ANGER: 0.60, EmotionKind.SMUG: 0.6, EmotionKind.SURPRISE: 0.50},
        ),
        SemanticExpressionUnit(
            id="嘴部居中",
            targets=[
                ExpressionTarget(action=SemanticAction.MOUTH_X, min_value=0, max_value=0),
            ],
            emotions={EmotionKind.SADNESS: 0.24},
        ),
        # —— 头部俯仰 ——
        SemanticExpressionUnit(
            id="抬头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_PITCH, min_value=0.3, max_value=0.7)],
            emotions={},
            baseline=0.05,
        ),
        SemanticExpressionUnit(
            id="低头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_PITCH, min_value=-0.7, max_value=-0.3)],
            emotions={
                EmotionKind.SADNESS: 0.68,
                EmotionKind.ANGER: 0.62,
                EmotionKind.SHY: 0.55,
            },
        ),
        # —— 头部侧歪 ——
        SemanticExpressionUnit(
            id="歪头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_ROLL, min_value=-0.5, max_value=0.5)],
            emotions={EmotionKind.JOY: 0.45, EmotionKind.WRY: 0.50, EmotionKind.SMUG: 0.35},
            baseline=0.25,
        ),
        # —— 头部转向 ——
        SemanticExpressionUnit(
            id="转头",
            targets=[ExpressionTarget(action=SemanticAction.HEAD_YAW, min_value=-0.5, max_value=0.5)],
            emotions={},
            baseline=0.20,
        ),
        # —— 复合 AU：低头 + 抬眼的合取，整体持有 smug 身份 ——
        SemanticExpressionUnit(
            id="阴险抬眼",
            targets=[
                ExpressionTarget(action=SemanticAction.HEAD_PITCH, min_value=-0.60, max_value=-0.30),
                ExpressionTarget(action=SemanticAction.EYE_GAZE_Y, min_value=0.60, max_value=1.00),
            ],
            emotions={EmotionKind.SMUG: 0.80, EmotionKind.ANGER: 0.55},
        ),
    ]


def default_rules() -> list[ExpressionRule]:
    """默认规则为空（v3）。

    历史上靠 rules 兜底的三类合理性约束，现分别由更底层的机制覆盖：
    - 物理互斥 → action 隐式冲突（旧「wink 左右互斥」为其冗余实例，已删）
    - 身份错位 → 典型度门（旧 Penalty「抿嘴削弱嘴角上扬」本为死规则，已删）
    - 合取语义 → 复合 AU（旧 Binding「怒视依赖」→ 复合 AU「阴险抬眼」，已删）
    - 拉郎配 → 同列高分同现由打分自然驱动，Bonus 无选择效果，已删

    规则类型与执行代码保留三类作为模型级例外通道：MutualExclusion（互斥）、
    Binding（绑定，penalty=∞ 强制）、Bonus（加分，value 带符号，正加负扣——
    旧 PenaltyRule 已并入此类）。仅当某模型出现「同列都典型、物理不冲突、
    但美术上不能同现」的真例外时，才按需添加 MutualExclusionRule。
    """

    return []

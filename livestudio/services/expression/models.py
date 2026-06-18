"""表情解算层运行时数据模型"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from livestudio.services.semantic_actions.models import (
    DEFAULT_SEMANTIC_ACTION_SPECS,
    FacialRegion,
    SemanticAction,
    SemanticActionSpec,
)

_SPEC_BY_ACTION: dict[str, SemanticActionSpec] = {
    spec.id: spec for spec in DEFAULT_SEMANTIC_ACTION_SPECS
}


class EmotionKind(StrEnum):
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class ExpressionTarget:
    action: SemanticAction
    min_value: float
    max_value: float  # >= min_value


@dataclass(frozen=True, slots=True)
class SemanticExpressionUnit:
    """通过 SemanticAction 驱动参数的 AU，区域由 targets 的 action 自动推导"""

    id: str
    targets: list[ExpressionTarget]
    emotions: dict[EmotionKind, float]  # 正数 (0,1]；缺失或 <=0 视为无关
    easing: str = "out_cubic"
    activation_threshold: float = 0.05

    @property
    def regions(self) -> frozenset[FacialRegion]:
        return frozenset(
            _SPEC_BY_ACTION[t.action].region
            for t in self.targets
            if t.action in _SPEC_BY_ACTION
        )


@dataclass(frozen=True, slots=True)
class NativeExpressionUnit:
    """直接触发平台原生表情（如 VTS .exp3.json）的 AU"""

    id: str
    platform: str
    native_ref: str
    regions: frozenset[FacialRegion]
    emotions: dict[EmotionKind, float]
    activation_threshold: float = 0.05


ExpressionUnit = SemanticExpressionUnit | NativeExpressionUnit


# ── 规则 ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class MutualExclusionRule:
    """unit_ids 中的 AU 不能同时出现"""

    id: str
    unit_ids: frozenset[str]
    emotions: frozenset[EmotionKind] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class BonusRule:
    """unit_ids 中的 AU 全部出现时，组合得分 +value"""

    id: str
    unit_ids: frozenset[str]
    value: float
    emotions: frozenset[EmotionKind] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class PenaltyRule:
    """unit_ids 中的 AU 全部出现时，组合得分 -value"""

    id: str
    unit_ids: frozenset[str]
    value: float
    emotions: frozenset[EmotionKind] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class BindingRule:
    """unit_ids 中任意 AU 出现时，其余 AU 也应出现；否则扣 penalty 分"""

    id: str
    unit_ids: frozenset[str]
    penalty: float = float("inf")  # inf = 强制，缺席则组合非法
    emotions: frozenset[EmotionKind] = field(default_factory=frozenset)


ExpressionRule = MutualExclusionRule | BonusRule | PenaltyRule | BindingRule


# ── 解算中间体 & 输出 ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class ScoredExpressionUnit:
    unit: ExpressionUnit
    score: float
    correlation: float


@dataclass(frozen=True, slots=True)
class ExpressionRequest:
    emotion: EmotionKind
    randomness: float = 0.5
    diversity: float = 0.6
    history_avoidance: float = 0.7
    duration_scale: float = 1.0
    max_units: int = 5
    min_au_score: float = 0.08
    core_score: float = 0.65


@dataclass(frozen=True, slots=True)
class ResolvedSemanticTarget:
    action: str
    value: float  # 已采样，直接用作 end_value
    easing: str = "out_cubic"  # 来自所属 AU，调用方直接用作 tween easing


@dataclass(frozen=True, slots=True)
class NativeExpressionTrigger:
    platform: str
    native_ref: str


@dataclass(slots=True)
class SelectedExpression:
    units: list[ExpressionUnit]
    emotion: EmotionKind
    score: float
    semantic_targets: list[ResolvedSemanticTarget]
    native_triggers: list[NativeExpressionTrigger]
    units_by_region: dict[FacialRegion, list[ExpressionUnit]]


@dataclass(frozen=True, slots=True)
class ExpressionSignature:
    unit_ids: frozenset[str]
    emotion: EmotionKind

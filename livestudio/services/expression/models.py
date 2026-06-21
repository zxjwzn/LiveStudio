"""表情解算层数据模型

定义类（AU、规则、Target）用 frozen Pydantic：既能直接构造给 solver 用，
也能序列化进模型配置 YAML，单层不再区分 config / runtime。
纯运行时输入输出（Request/Result/Signature 等）保持轻量 dataclass。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class _FrozenModel(BaseModel):
    """定义类共用：不可变 + 拒绝未知字段"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ExpressionTarget(_FrozenModel):
    """单个语义动作目标，值域 [min_value, max_value]，解算时随机采样"""

    action: SemanticAction
    min_value: float
    max_value: float


class SemanticExpressionUnit(_FrozenModel):
    """通过 SemanticAction 驱动参数的 AU，区域由 targets 的 action 自动推导

    id 通常由 ExpressionProfileConfig.semantic_units 的字典键注入，
    直接构造时可省略（保持空串），solver 仍可独立使用。
    """

    id: str = ""
    enabled: bool = True
    targets: list[ExpressionTarget]
    emotions: dict[EmotionKind, float] = Field(
        default_factory=dict
    )  # 正数 (0,1]；缺失或 <=0 视为无关
    easing: str = "linear"
    activation_threshold: float = 0.05

    @property
    def regions(self) -> frozenset[FacialRegion]:
        return frozenset(
            _SPEC_BY_ACTION[t.action].region
            for t in self.targets
            if t.action in _SPEC_BY_ACTION
        )


class NativeExpressionUnit(_FrozenModel):
    """直接触发平台原生表情（如 VTS .exp3.json）的 AU"""

    id: str = ""
    enabled: bool = True
    platform: str
    native_ref: str
    regions: frozenset[FacialRegion]
    emotions: dict[EmotionKind, float] = Field(default_factory=dict)
    activation_threshold: float = 0.05


ExpressionUnit = SemanticExpressionUnit | NativeExpressionUnit


# ── 规则 ──────────────────────────────────────────────────────────────────────


class MutualExclusionRule(_FrozenModel):
    """unit_ids 中的 AU 不能同时出现"""

    kind: Literal["mutual_exclusion"] = "mutual_exclusion"
    id: str
    unit_ids: frozenset[str]
    emotions: frozenset[EmotionKind] = Field(default_factory=frozenset)


class BonusRule(_FrozenModel):
    """unit_ids 中的 AU 全部出现时，组合得分 +value"""

    kind: Literal["bonus"] = "bonus"
    id: str
    unit_ids: frozenset[str]
    value: float
    emotions: frozenset[EmotionKind] = Field(default_factory=frozenset)


class PenaltyRule(_FrozenModel):
    """unit_ids 中的 AU 全部出现时，组合得分 -value"""

    kind: Literal["penalty"] = "penalty"
    id: str
    unit_ids: frozenset[str]
    value: float
    emotions: frozenset[EmotionKind] = Field(default_factory=frozenset)


class BindingRule(_FrozenModel):
    """unit_ids 中任意 AU 出现时，其余 AU 也应出现；否则扣 penalty 分"""

    kind: Literal["binding"] = "binding"
    id: str
    unit_ids: frozenset[str]
    penalty: float = float("inf")  # inf = 强制，缺席则组合非法
    emotions: frozenset[EmotionKind] = Field(default_factory=frozenset)


ExpressionRule = Annotated[
    MutualExclusionRule | BonusRule | PenaltyRule | BindingRule,
    Field(discriminator="kind"),
]


# ── 纯运行时输入 / 中间体 / 输出（不序列化，保持 dataclass） ─────────────────────


@dataclass(slots=True)
class ScoredExpressionUnit:
    unit: ExpressionUnit
    score: float
    correlation: float


@dataclass(frozen=True, slots=True)
class ExpressionRequest:
    """solver 的解算输入；时序参数（过渡/保持时长）属于控制器，不在此处"""

    emotion: EmotionKind
    randomness: float = 0.5
    diversity: float = 0.6
    history_avoidance: float = 0.7
    max_units: int = 5
    min_au_score: float = 0.08
    core_score: float = 0.65


@dataclass(frozen=True, slots=True)
class ResolvedSemanticTarget:
    action: SemanticAction  # 透传所属 target 的语义动作枚举
    value: float  # 已采样，直接用作 end_value
    easing: str = "out_cubic"  # 来自所属 AU


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

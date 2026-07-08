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

_SPEC_BY_ACTION: dict[str, SemanticActionSpec] = {spec.id: spec for spec in DEFAULT_SEMANTIC_ACTION_SPECS}


class EmotionKind(StrEnum):
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    SURPRISE = "surprise"  # 惊讶
    SMUG = "smug"  # 阴险·得意
    WRY = "wry"  # 无奈·苦笑
    SHY = "shy"  # 害羞


class _FrozenModel(BaseModel):
    """定义类共用：不可变 + 拒绝未知字段"""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ExpressionTarget(_FrozenModel):
    """单个语义动作目标，值域 [min_value, max_value]，解算时随机采样"""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra={"title_field": "action", "icon": "ASTERISK"})

    action: SemanticAction
    min_value: float
    max_value: float


class SemanticExpressionUnit(_FrozenModel):
    """通过 SemanticAction 驱动参数的 AU，区域由 targets 的 action 自动推导

    id 通常由 ExpressionProfileConfig.semantic_units 的字典键注入，
    直接构造时可省略（保持空串），solver 仍可独立使用。
    """

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra={"title_field": "id", "icon": "EMOJI_TAB_SYMBOLS"})

    id: str = ""
    enabled: bool = True
    targets: list[ExpressionTarget]
    emotions: dict[EmotionKind, float] = Field(
        default_factory=dict
    )  # 正数 (0,1]；缺失走 baseline 兜底，显式 <=0 视为该情绪禁用
    baseline: float = 0.0  # 百搭分：情绪列未显式打分时的兜底相关性；0=非百搭
    easing: str = "linear"

    @property
    def regions(self) -> frozenset[FacialRegion]:
        return frozenset(_SPEC_BY_ACTION[t.action].region for t in self.targets if t.action in _SPEC_BY_ACTION)


class NativeExpressionUnit(_FrozenModel):
    """直接触发平台原生表情（如 VTS .exp3.json）的 AU"""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra={"title_field": "id", "icon": "ALBUM"})

    id: str = ""
    enabled: bool = True
    platform: str
    native_ref: str
    regions: frozenset[FacialRegion]
    emotions: dict[EmotionKind, float] = Field(default_factory=dict)
    baseline: float = 0.0  # 百搭分：语义同 SemanticExpressionUnit.baseline


ExpressionUnit = SemanticExpressionUnit | NativeExpressionUnit


# ── 规则 ──────────────────────────────────────────────────────────────────────


class MutualExclusionRule(_FrozenModel):
    """unit_ids 中的 AU 不能同时出现"""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra={"title_field": "id", "icon": "CANCEL"})

    kind: Literal["mutual_exclusion"] = "mutual_exclusion"
    id: str
    unit_ids: frozenset[str]
    emotions: frozenset[EmotionKind] = Field(default_factory=frozenset)


class BonusRule(_FrozenModel):
    """unit_ids 中的 AU 全部出现时，组合得分 += value（value 为负即扣分，已合并旧 PenaltyRule）"""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_extra={"title_field": "id", "icon": "ADD"})

    kind: Literal["bonus"] = "bonus"
    id: str
    unit_ids: frozenset[str]
    value: float
    emotions: frozenset[EmotionKind] = Field(default_factory=frozenset)


ExpressionRule = Annotated[
    MutualExclusionRule | BonusRule,
    Field(discriminator="kind"),
]


# ── 纯运行时输入 / 中间体 / 输出（不序列化，保持 dataclass） ─────────────────────


@dataclass(slots=True)
class ScoredExpressionUnit:
    unit: ExpressionUnit
    score: float
    correlation: float
    typicality: float = 1.0  # 本职程度 = correlation / 打分行峰值，值域 (0,1]
    via_baseline: bool = False  # correlation 是否来自百搭分


@dataclass(frozen=True, slots=True)
class ExpressionRequest:
    """solver 的解算输入；时序参数（过渡/保持时长）属于控制器，不在此处"""

    emotion: EmotionKind
    intensity: float = 1.0  # 表情强度：0→全脸回 neutral，1→完整表情
    randomness: float = 0.5
    diversity: float = 0.6
    history_avoidance: float = 0.7
    max_units: int = 5
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

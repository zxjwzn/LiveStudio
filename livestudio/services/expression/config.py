"""表情解算层可持久化配置模型"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.expression.models import (
    BindingRule,
    BonusRule,
    EmotionKind,
    ExpressionRequest,
    ExpressionRule,
    ExpressionTarget,
    ExpressionUnit,
    MutualExclusionRule,
    NativeExpressionUnit,
    PenaltyRule,
    SemanticExpressionUnit,
)
from livestudio.services.semantic_actions.models import FacialRegion, SemanticAction


class ExpressionTargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    min_value: float
    max_value: float

    def to_target(self) -> ExpressionTarget:
        return ExpressionTarget(
            action=SemanticAction(self.action),
            min_value=self.min_value,
            max_value=self.max_value,
        )


class SemanticUnitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    targets: list[ExpressionTargetConfig]
    emotions: dict[str, float] = Field(default_factory=dict)
    easing: str | None = None  # 为空时回退到 runtime.default_easing
    activation_threshold: float = 0.05

    def to_unit(
        self, unit_id: str, default_easing: str = "out_cubic"
    ) -> SemanticExpressionUnit | None:
        if not self.enabled:
            return None
        return SemanticExpressionUnit(
            id=unit_id,
            targets=[t.to_target() for t in self.targets],
            emotions={EmotionKind(k): v for k, v in self.emotions.items()},
            easing=self.easing or default_easing,
            activation_threshold=self.activation_threshold,
        )


class NativeUnitConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    platform: str
    native_ref: str
    regions: list[str]
    emotions: dict[str, float] = Field(default_factory=dict)
    activation_threshold: float = 0.05

    def to_unit(self, unit_id: str) -> NativeExpressionUnit | None:
        if not self.enabled:
            return None
        return NativeExpressionUnit(
            id=unit_id,
            platform=self.platform,
            native_ref=self.native_ref,
            regions=frozenset(FacialRegion(r) for r in self.regions),
            emotions={EmotionKind(k): v for k, v in self.emotions.items()},
            activation_threshold=self.activation_threshold,
        )


# ── 规则配置 ──────────────────────────────────────────────────────────────────


class MutualExclusionRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["mutual_exclusion"]
    id: str
    unit_ids: list[str]
    emotions: list[str] = Field(default_factory=list)

    def to_rule(self) -> MutualExclusionRule:
        return MutualExclusionRule(
            id=self.id,
            unit_ids=frozenset(self.unit_ids),
            emotions=frozenset(EmotionKind(e) for e in self.emotions),
        )


class BonusRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["bonus"]
    id: str
    unit_ids: list[str]
    value: float
    emotions: list[str] = Field(default_factory=list)

    def to_rule(self) -> BonusRule:
        return BonusRule(
            id=self.id,
            unit_ids=frozenset(self.unit_ids),
            value=self.value,
            emotions=frozenset(EmotionKind(e) for e in self.emotions),
        )


class PenaltyRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["penalty"]
    id: str
    unit_ids: list[str]
    value: float
    emotions: list[str] = Field(default_factory=list)

    def to_rule(self) -> PenaltyRule:
        return PenaltyRule(
            id=self.id,
            unit_ids=frozenset(self.unit_ids),
            value=self.value,
            emotions=frozenset(EmotionKind(e) for e in self.emotions),
        )


class BindingRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["binding"]
    id: str
    unit_ids: list[str]
    penalty: float = float("inf")
    emotions: list[str] = Field(default_factory=list)

    def to_rule(self) -> BindingRule:
        return BindingRule(
            id=self.id,
            unit_ids=frozenset(self.unit_ids),
            penalty=self.penalty,
            emotions=frozenset(EmotionKind(e) for e in self.emotions),
        )


ExpressionRuleConfig = Annotated[
    MutualExclusionRuleConfig | BonusRuleConfig | PenaltyRuleConfig | BindingRuleConfig,
    Field(discriminator="kind"),
]


# ── Runtime & Profile ─────────────────────────────────────────────────────────


class ExpressionRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_units: int = 5
    randomness: float = 0.5
    diversity: float = 0.6
    history_avoidance: float = 0.7
    duration_scale: float = 1.0
    min_au_score: float = 0.08
    core_score: float = 0.65
    default_easing: str = "out_cubic"  # SemanticUnitConfig 未指定 easing 时的后备值
    history_capacity: int = 20
    top_candidates: int = 14


class ExpressionProfileConfig(BaseModel):
    """模型级表情配置，加载时以配置文件内容为准，不做自动补全"""

    model_config = ConfigDict(extra="forbid")

    runtime: ExpressionRuntimeConfig = Field(default_factory=ExpressionRuntimeConfig)
    semantic_units: dict[str, SemanticUnitConfig] = Field(default_factory=dict)
    native_units: dict[str, NativeUnitConfig] = Field(default_factory=dict)
    rules: list[ExpressionRuleConfig] = Field(default_factory=list)

    def to_units(self) -> list[ExpressionUnit]:
        """返回所有 enabled=True 的运行时 AU"""
        result: list[ExpressionUnit] = []
        for uid, cfg in self.semantic_units.items():
            unit = cfg.to_unit(uid, self.runtime.default_easing)
            if unit is not None:
                result.append(unit)
        for uid, cfg in self.native_units.items():
            unit = cfg.to_unit(uid)
            if unit is not None:
                result.append(unit)
        return result

    def to_rules(self) -> list[ExpressionRule]:
        return [r.to_rule() for r in self.rules]

    def build_request(
        self, emotion: EmotionKind, **overrides: object
    ) -> ExpressionRequest:
        """用 runtime 默认值填充未传入的字段"""
        rt = self.runtime
        defaults: dict[str, object] = {
            "randomness": rt.randomness,
            "diversity": rt.diversity,
            "history_avoidance": rt.history_avoidance,
            "duration_scale": rt.duration_scale,
            "max_units": rt.max_units,
            "min_au_score": rt.min_au_score,
            "core_score": rt.core_score,
        }
        defaults.update(overrides)
        return ExpressionRequest(emotion=emotion, **defaults)  # type: ignore[arg-type]

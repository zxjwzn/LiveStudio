"""表情解算层模型级配置入口

AU 与规则的定义已合并到 models.py 的单层 Pydantic 模型，这里只保留
模型级聚合（runtime 参数 + AU 列表 + 规则列表）与展开成运行时列表。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.expression.models import (
    EmotionKind,
    ExpressionRequest,
    ExpressionRule,
    ExpressionUnit,
    NativeExpressionUnit,
    SemanticExpressionUnit,
)


class ExpressionRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_units: int = 5
    randomness: float = 0.5
    diversity: float = 0.6
    history_avoidance: float = 0.7
    transition_duration: float = 0.5  # 解算后切换到目标表情的过渡时长
    hold_duration: float = 1.5  # 到达后保持时长，期间锁定参数
    min_au_score: float = 0.08
    core_score: float = 0.65
    history_capacity: int = 20
    top_candidates: int = 14


class ExpressionProfileConfig(BaseModel):
    """模型级表情配置，加载时以配置文件内容为准，不做自动补全

    AU 自带 id，semantic_units / native_units 以列表存储。
    """

    model_config = ConfigDict(extra="forbid")

    runtime: ExpressionRuntimeConfig = Field(default_factory=ExpressionRuntimeConfig)
    semantic_units: list[SemanticExpressionUnit] = Field(default_factory=list)
    native_units: list[NativeExpressionUnit] = Field(default_factory=list)
    rules: list[ExpressionRule] = Field(default_factory=list)

    def to_units(self) -> list[ExpressionUnit]:
        """返回所有 enabled=True 的 AU；校验 id 非空且唯一"""
        result: list[ExpressionUnit] = []
        seen: set[str] = set()
        for unit in (*self.semantic_units, *self.native_units):
            if not unit.id:
                raise ValueError("表情 AU 缺少 id")
            if unit.id in seen:
                raise ValueError(f"表情 AU id 重复: {unit.id}")
            seen.add(unit.id)
            if unit.enabled:
                result.append(unit)
        return result

    def to_rules(self) -> list[ExpressionRule]:
        return list(self.rules)

    def build_request(self, emotion: EmotionKind, **overrides: object) -> ExpressionRequest:
        """用 runtime 默认值填充未传入的字段"""
        rt = self.runtime
        defaults: dict[str, object] = {
            "randomness": rt.randomness,
            "diversity": rt.diversity,
            "history_avoidance": rt.history_avoidance,
            "transition_duration": rt.transition_duration,
            "hold_duration": rt.hold_duration,
            "max_units": rt.max_units,
            "min_au_score": rt.min_au_score,
            "core_score": rt.core_score,
        }
        defaults.update(overrides)
        return ExpressionRequest(emotion=emotion, **defaults)  # type: ignore[arg-type]

    @classmethod
    def with_default_units(cls) -> "ExpressionProfileConfig":
        """构造带内置默认语义 AU 与规则的 profile（仅首次初始化配置文件时用）"""
        from .defaults import default_rules, default_semantic_units

        return cls(semantic_units=default_semantic_units(), rules=default_rules())

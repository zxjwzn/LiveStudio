"""表情解算层模型级配置入口

AU 与规则的定义已合并到 models.py 的单层 Pydantic 模型，这里只保留
模型级聚合（AU 列表 + 规则列表）与展开成运行时列表。

解算参数（randomness/diversity/max_units 等）不在这里：它们是 ExpressionRequest
的字段，默认值就在 ExpressionRequest 上，需要调时直接构造或覆盖即可。solver 的
构造参数（history_capacity/top_candidates）与 au_priority 归 ExpressionControllerSettings。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.expression.models import (
    ExpressionRule,
    ExpressionUnit,
    NativeExpressionUnit,
    SemanticExpressionUnit,
)


class ExpressionProfileConfig(BaseModel):
    """模型级表情配置，加载时以配置文件内容为准，不做自动补全

    AU 自带 id，semantic_units / native_units 以列表存储。
    """

    model_config = ConfigDict(extra="forbid")

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

    @classmethod
    def with_default_units(cls) -> "ExpressionProfileConfig":
        """构造带内置默认语义 AU 与规则的 profile（仅首次初始化配置文件时用）"""
        from .defaults import default_rules, default_semantic_units

        return cls(semantic_units=default_semantic_units(), rules=default_rules())

"""VTube Studio 平台服务配置模型"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from livestudio.services.platforms.model_config import PlatformModelConfig
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticActionBinding,
)

from .semantic import (
    default_vtube_studio_parameter_specs,
    default_vtube_studio_semantic_bindings,
)


class VTubeStudioExpressionStateConfig(BaseModel):
    """VTube Studio 表情激活状态配置"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", description="表情名称")
    file: str = Field(default="", description="表情文件名")
    active: bool = Field(default=False, description="模型加载时是否激活该表情")


class VTubeStudioModelConfig(PlatformModelConfig):
    """按 VTube Studio 模型持久化的完整平台配置"""

    model_config = ConfigDict(extra="forbid")

    expressions: list[VTubeStudioExpressionStateConfig] = Field(
        default_factory=list,
        description="模型加载时需要同步的表情激活状态配置",
    )

    @field_validator("expressions", mode="before")
    @classmethod
    def migrate_expression_mapping(cls, value: Any) -> Any:
        """兼容旧版按文件名索引的表情配置"""

        if isinstance(value, dict):
            return list(value.values())
        return value

    def ensure_semantic_profile_defaults(
        self,
        bindings: Iterable[SemanticActionBinding] | None = None,
    ) -> bool:
        """补齐当前模型的语义动作映射默认值"""

        changed = False
        if self.semantic_profile.model_id != self.model.model_id:
            self.semantic_profile.model_id = self.model.model_id
            changed = True
        if self.semantic_profile.model_name != self.model.model_name:
            self.semantic_profile.model_name = self.model.model_name
            changed = True
        return (
            super().ensure_semantic_profile_defaults(
                bindings or default_vtube_studio_semantic_bindings(),
            )
            or changed
        )

    def ensure_parameter_spec_defaults(
        self,
        specs: Iterable[PlatformParameterSpec] | None = None,
    ) -> bool:
        """补齐当前模型缺失的 VTube Studio 参数范围默认值"""

        return super().ensure_parameter_spec_defaults(
            specs or default_vtube_studio_parameter_specs(),
        )

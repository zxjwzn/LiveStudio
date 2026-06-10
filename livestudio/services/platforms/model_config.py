"""按模型保存的跨平台配置"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.animations.controllers import AnimationControllerSettingsConfig
from livestudio.services.expressions.models import ExpressionProfileConfig
from livestudio.services.expressions.profile import default_expression_profile
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticActionBinding,
    SemanticActionProfile,
)

from .model import PlatformModelIdentity


class PlatformModelConfig(BaseModel):
    """每个模型都会保存的基础配置"""

    model_config = ConfigDict(extra="forbid")

    model: PlatformModelIdentity = Field(
        default_factory=lambda: PlatformModelIdentity(
            platform_name="",
            model_id="",
            model_name="",
        ),
        description="这份配置属于哪个平台模型",
    )
    semantic_profile: SemanticActionProfile = Field(
        default_factory=SemanticActionProfile,
        description="通用动作到模型参数的对应关系",
    )
    parameter_specs: list[PlatformParameterSpec] = Field(
        default_factory=list,
        description="通用动作转换时会用到的模型参数范围",
    )
    controllers: AnimationControllerSettingsConfig = Field(
        default_factory=AnimationControllerSettingsConfig,
        description="各平台都能用的动画控制器设置",
    )
    expression_profile: ExpressionProfileConfig = Field(
        default_factory=default_expression_profile,
        description="当前模型自己的 AU、规则和解算运行时配置",
    )

    def sync_identity(self, identity: PlatformModelIdentity) -> bool:
        """同步保存的模型身份和动作配置元信息"""

        changed = False
        if self.model != identity:
            self.model = identity
            changed = True
        if self.semantic_profile.model_id != identity.model_id:
            self.semantic_profile.model_id = identity.model_id
            changed = True
        if self.semantic_profile.model_name != identity.model_name:
            self.semantic_profile.model_name = identity.model_name
            changed = True
        return changed

    def ensure_semantic_profile_defaults(
        self,
        bindings: Iterable[SemanticActionBinding],
    ) -> bool:
        """用平台默认值补齐缺少的动作对应关系"""

        return self.semantic_profile.ensure_defaults(bindings=bindings)

    def ensure_parameter_spec_defaults(
        self,
        specs: Iterable[PlatformParameterSpec],
    ) -> bool:
        """用平台默认值补齐缺少的参数范围"""

        existing_names = {spec.name for spec in self.parameter_specs}
        missing = [spec for spec in specs if spec.name not in existing_names]
        if not missing:
            return False
        self.parameter_specs.extend(missing)
        return True

    def ensure_expression_profile_defaults(self) -> bool:
        """用内置 AU catalog 和规则补齐当前模型缺失的表情配置"""

        return self.expression_profile.ensure_defaults(default_expression_profile())

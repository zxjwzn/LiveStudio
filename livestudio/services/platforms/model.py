"""平台服务运行时模型"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.animations.controllers import AnimationControllerSettingsConfig
from livestudio.services.expression import ExpressionProfileConfig
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticActionProfile,
)


class PlatformModelIdentity(BaseModel):
    """平台当前加载模型的运行时身份"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "FINGERPRINT"})

    platform_name: str = Field(description="平台唯一名称")
    model_id: str = Field(description="平台模型唯一 ID")
    model_name: str = Field(description="平台模型显示名称")


class PlatformModelConfig(BaseModel):
    """每个模型都会保存的基础配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SETTING"})

    model: PlatformModelIdentity = Field(
        default_factory=lambda: PlatformModelIdentity(
            platform_name="",
            model_id="",
            model_name="",
        ),
        description="这份配置属于哪个平台模型",
    )
    controllers: AnimationControllerSettingsConfig = Field(
        default_factory=AnimationControllerSettingsConfig,
        description="各平台都能用的动画控制器设置",
    )
    semantic_profile: SemanticActionProfile = Field(
        default_factory=SemanticActionProfile,
        description="通用动作到模型参数的对应关系",
    )
    parameter_specs: list[PlatformParameterSpec] = Field(
        default_factory=list,
        description="通用动作转换时会用到的模型参数范围",
    )
    expression_profile: ExpressionProfileConfig = Field(
        default_factory=ExpressionProfileConfig,
        description="情绪驱动的表情解算配置（AU、规则、运行时参数）；seed-once（语义 B），文件存在后完全以文件为准",
    )

    @classmethod
    def create_default(cls, identity: PlatformModelIdentity) -> Self:
        """构造一份完整的默认模型配置（仅在配置文件首次生成时用）。

        这里写入平台无关的内置表情 AU 与规则，作为用户后续微调的起点；
        配置文件存在后加载完全以文件为准。子类覆盖时应基于本方法的结果再
        填充平台相关默认（见 VTubeStudioModelConfig.create_default）。
        """

        return cls(
            model=identity,
            expression_profile=ExpressionProfileConfig.create_default(),
        )

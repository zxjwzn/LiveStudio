"""VTube Studio 平台服务配置模型"""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.platforms.model import PlatformModelConfig, PlatformModelIdentity

from .defaults import (
    default_vtube_studio_parameter_specs,
    default_vtube_studio_semantic_profile,
)


class VTubeStudioExpressionStateConfig(BaseModel):
    """VTube Studio 表情激活状态配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"title_field": "name", "icon": "EMOJI_TAB_SYMBOLS"})

    name: str = Field(default="", description="表情名称")
    file: str = Field(default="", description="表情文件名")
    active: bool = Field(default=False, description="模型加载时是否激活该表情")


class VTubeStudioModelConfig(PlatformModelConfig):
    """按 VTube Studio 模型持久化的完整平台配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SETTING"})

    expressions: list[VTubeStudioExpressionStateConfig] = Field(
        default_factory=list,
        description="模型加载时需要同步的表情激活状态配置",
    )

    @classmethod
    def create_default(cls, identity: PlatformModelIdentity) -> Self:
        """构造 VTube Studio 模型的完整默认配置（仅首次创建配置文件时使用）。

        在基类默认表情之上，再种入 VTS 专属的语义绑定与参数范围。
        """

        base = PlatformModelConfig.create_default(identity)
        data = base.model_dump()
        data.pop("semantic_profile", None)
        data.pop("parameter_specs", None)
        return cls(
            **data,
            semantic_profile=default_vtube_studio_semantic_profile(),
            parameter_specs=default_vtube_studio_parameter_specs(),
        )

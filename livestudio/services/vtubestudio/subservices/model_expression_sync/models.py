from pydantic import BaseModel, ConfigDict, Field

from ..base import SubserviceConfigFile


class ManagedExpressionConfig(BaseModel):
    """单个表情的持久化配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="表情名称。")
    file: str = Field(min_length=1, description="表情文件名。")
    active: bool = Field(description="是否在模型加载后激活。")


class ManagedModelExpressionConfig(BaseModel):
    """单个模型的表情配置文件。"""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(
        default="UnknownModel",
        min_length=1,
        description="模型名称。",
    )
    model_id: str = Field(
        default="UnknownModelID",
        min_length=1,
        description="模型 ID。",
    )
    expressions: list[ManagedExpressionConfig] = Field(
        default_factory=list,
        description="该模型的表情激活配置。",
    )


class ModelExpressionSyncConfig(BaseModel):
    """模型表情同步逻辑配置。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="是否启用模型表情同步逻辑。")
    sync_on_startup: bool = Field(
        default=True,
        description="服务启动后是否立即同步当前模型表情。",
    )
    activation_fade_time: float = Field(
        default=0.25,
        ge=0,
        le=2,
        description="表情切换淡入时长。",
    )


class ModelExpressionSyncConfigFile(SubserviceConfigFile[ModelExpressionSyncConfig]):
    """模型表情同步子服务配置文件。"""

    config: ModelExpressionSyncConfig = Field(default_factory=ModelExpressionSyncConfig)

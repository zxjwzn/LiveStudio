from pydantic import BaseModel, ConfigDict, Field


class ModelExpressionEntry(BaseModel):
    """单个表情的激活配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="表情名称。")
    file: str = Field(description="表情文件名。")
    active: bool = Field(default=False, description="切换到该模型时是否自动激活。")


class ModelExpressionConfig(BaseModel):
    """按模型保存的表情配置文件。"""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(default="", description="VTS 模型 ID。")
    model_name: str = Field(default="", description="VTS 模型名称。")
    expressions: list[ModelExpressionEntry] = Field(default_factory=list, description="模型全部表情及目标激活状态。")
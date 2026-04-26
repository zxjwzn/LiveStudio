from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from livestudio.tween import TweenRequest

TemplatePrimitive: TypeAlias = float | int | bool | str
TemplateValue: TypeAlias = TemplatePrimitive | dict[str, str | list[float | int]]
TemplateScalar: TypeAlias = TemplatePrimitive


class TemplateParameterDefinition(BaseModel):
    """模板可接收的外部参数声明。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="参数名。")
    description: str | None = Field(default=None, description="参数说明。")
    type: str | None = Field(default=None, description="参数类型声明。")
    default: TemplateValue | None = Field(default=None, description="默认值。")
    required: bool = Field(default=False, description="是否必须传入。")


class TemplateActionDefinition(BaseModel):
    """模板中的单个参数动作。"""

    model_config = ConfigDict(extra="forbid")

    parameter: str = Field(min_length=1, description="目标参数名。")
    to: TemplateValue = Field(description="目标值。")
    duration: TemplateValue = Field(default=0.0, description="动作时长。")
    from_value: TemplateValue | None = Field(
        default=None,
        alias="from",
        description="可选起始值。",
    )
    delay: TemplateValue = Field(default=0.0, description="动作延迟。")
    easing: str = Field(default="linear", description="缓动函数名。")
    mode: Literal["set", "add"] = Field(default="set", description="参数写入模式。")


class TemplateDataDefinition(BaseModel):
    """模板主体。"""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(default=None, description="模板说明。")
    params: list[TemplateParameterDefinition] = Field(
        default_factory=list,
        description="外部参数声明。",
    )
    variables: dict[str, TemplateValue] = Field(
        default_factory=dict,
        description="内部变量定义。",
    )
    actions: list[TemplateActionDefinition] = Field(
        default_factory=list,
        description="动作列表。",
    )


class AnimationTemplate(BaseModel):
    """动画模板文件结构。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="模板名称。")
    type: Literal["animation"] = Field(default="animation", description="模板类型。")
    data: TemplateDataDefinition = Field(
        default_factory=TemplateDataDefinition,
        description="模板主体数据。",
    )


class LoadedTemplateParameterInfo(BaseModel):
    """已加载模板参数摘要。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="参数名。")
    type: str | None = Field(default=None, description="参数类型声明。")
    description: str | None = Field(default=None, description="参数说明。")


class LoadedTemplateInfo(BaseModel):
    """已加载动画模板摘要。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="模板名称。")
    description: str | None = Field(default=None, description="模板说明。")
    parameter_count: int = Field(default=0, ge=0, description="参数数量。")
    variable_count: int = Field(default=0, ge=0, description="变量数量。")
    action_count: int = Field(default=0, ge=0, description="动作数量。")
    parameters: list[LoadedTemplateParameterInfo] = Field(
        default_factory=list,
        description="模板参数摘要列表。",
    )


class TemplatePlayback(BaseModel):
    """一次模板渲染结果。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    template_name: str = Field(min_length=1, description="模板名称。")
    context: dict[str, TemplateScalar] = Field(
        default_factory=dict,
        description="求值上下文。",
    )
    actions: list[TweenRequest] = Field(
        default_factory=list,
        description="动作列表。",
    )

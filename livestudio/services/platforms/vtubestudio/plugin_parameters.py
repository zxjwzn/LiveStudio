"""VTube Studio 插件参数常量"""

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.semantic_actions import SemanticAction


class PluginParameterSpec(BaseModel):
    """VTube Studio 插件自定义参数定义。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=4, max_length=32)
    minimum: float = Field(ge=-1000000, le=1000000)
    maximum: float = Field(ge=-1000000, le=1000000)
    default: float = Field(ge=-1000000, le=1000000)
    explanation: str | None = Field(default=None, max_length=255)


PLUGIN_PARAMETER_TABLE: tuple[tuple[SemanticAction, PluginParameterSpec], ...] = (
    (
        SemanticAction.EYE_WIDE,
        PluginParameterSpec(
            name="EyeWide",
            minimum=0.0,
            maximum=1.0,
            default=0.0,
            explanation="LiveStudio eye wide control",
        ),
    ),
    (
        SemanticAction.MOUTH_JAW_OPEN,
        PluginParameterSpec(
            name="JawOpen",
            minimum=0.0,
            maximum=1.0,
            default=0.0,
            explanation="LiveStudio jaw open control",
        ),
    ),
    (
        SemanticAction.MOUTH_FUNNEL,
        PluginParameterSpec(
            name="MouthFunnel",
            minimum=0.0,
            maximum=1.0,
            default=0.0,
            explanation="LiveStudio mouth funnel control",
        ),
    ),
    (
        SemanticAction.MOUTH_PUCKER,
        PluginParameterSpec(
            name="MouthPucker",
            minimum=-1.0,
            maximum=1.0,
            default=0.0,
            explanation="LiveStudio mouth pucker control",
        ),
    ),
    (
        SemanticAction.MOUTH_SHRUG,
        PluginParameterSpec(
            name="MouthShrug",
            minimum=0.0,
            maximum=1.0,
            default=0.0,
            explanation="LiveStudio mouth shrug control",
        ),
    ),
)

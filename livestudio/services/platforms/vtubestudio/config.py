"""VTube Studio 平台服务配置模型"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.platforms.model import PlatformModelConfig
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticAction,
    SemanticActionBinding,
    SemanticActionProfile,
)


def default_vtube_studio_parameter_specs() -> list[PlatformParameterSpec]:
    """返回 VTube Studio 常用跟踪参数的范围"""

    return [
        PlatformParameterSpec(name="FacePositionX", minimum=-15.0, maximum=15.0),
        PlatformParameterSpec(name="FacePositionY", minimum=-15.0, maximum=15.0),
        PlatformParameterSpec(name="FacePositionZ", minimum=-10.0, maximum=10.0),
        PlatformParameterSpec(name="FaceAngleX", minimum=-30.0, maximum=30.0),
        PlatformParameterSpec(name="FaceAngleY", minimum=-30.0, maximum=30.0),
        PlatformParameterSpec(name="FaceAngleZ", minimum=-90.0, maximum=90.0),
        PlatformParameterSpec(name="MouthSmile", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="MouthOpen", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="Brows", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="BrowLeftY", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="BrowRightY", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="EyeOpenLeft", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="EyeOpenRight", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="EyeLeftX", minimum=-1.0, maximum=1.0),
        PlatformParameterSpec(name="EyeLeftY", minimum=-1.0, maximum=1.0),
        PlatformParameterSpec(name="EyeRightX", minimum=-1.0, maximum=1.0),
        PlatformParameterSpec(name="EyeRightY", minimum=-1.0, maximum=1.0),
        PlatformParameterSpec(name="MousePositionX", minimum=-1.0, maximum=1.0),
        PlatformParameterSpec(name="MousePositionY", minimum=-1.0, maximum=1.0),
        PlatformParameterSpec(name="MouthX", minimum=-1.0, maximum=1.0),
    ]


def default_vtube_studio_semantic_profile() -> SemanticActionProfile:
    bindings = [
        SemanticActionBinding(
            action=SemanticAction.BROW_HEIGHT,
            platform_params=["Brows"],
        ),
        SemanticActionBinding(
            action=SemanticAction.BROW_HEIGHT_LEFT,
            platform_params=["BrowLeftY"],
        ),
        SemanticActionBinding(
            action=SemanticAction.BROW_HEIGHT_RIGHT,
            platform_params=["BrowRightY"],
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_OPEN,
            platform_params=["EyeOpenLeft", "EyeOpenRight"],
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_OPEN_LEFT,
            platform_params=["EyeOpenLeft"],
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_OPEN_RIGHT,
            platform_params=["EyeOpenRight"],
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_GAZE_X,
            platform_params=["EyeLeftX", "EyeRightX"],
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_GAZE_Y,
            platform_params=["EyeLeftY", "EyeRightY"],
        ),
        SemanticActionBinding(
            action=SemanticAction.MOUTH_OPEN,
            platform_params=["MouthOpen"],
        ),
        SemanticActionBinding(
            action=SemanticAction.MOUTH_SMILE,
            platform_params=["MouthSmile"],
        ),
        SemanticActionBinding(
            action=SemanticAction.MOUTH_X,
            platform_params=["MouthX"],
        ),
        SemanticActionBinding(
            action=SemanticAction.HEAD_YAW,
            platform_params=["FaceAngleX"],
        ),
        SemanticActionBinding(
            action=SemanticAction.HEAD_PITCH,
            platform_params=["FaceAngleY"],
        ),
        SemanticActionBinding(
            action=SemanticAction.HEAD_ROLL,
            platform_params=["FaceAngleZ"],
        ),
    ]
    return SemanticActionProfile(
        bindings=bindings,
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

    def init_defaults(self) -> None:
        self.semantic_profile = default_vtube_studio_semantic_profile()
        self.parameter_specs = default_vtube_studio_parameter_specs()

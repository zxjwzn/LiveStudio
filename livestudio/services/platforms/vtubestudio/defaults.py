"""VTube Studio 平台相关的默认配置工厂

仅作为模型配置文件首次创建时的种子（见 VTubeStudioModelConfig.create_default）。
配置文件一旦存在，加载时完全以文件内容为准，不再引用这里的默认值。

与 expression/defaults.py 同构：所有默认工厂统一放在本模块，命名一律 default_*()，
每次调用返回新实例，避免共享可变状态。
"""

from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionBinding,
    SemanticActionProfile,
)


def default_vtube_studio_semantic_profile() -> SemanticActionProfile:
    """返回 VTube Studio 通用动作到模型参数的默认绑定"""

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

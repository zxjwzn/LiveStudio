"""VTube Studio 平台相关的默认配置工厂

仅作为模型配置文件首次创建时的种子（见 VTubeStudioModelConfig.create_default）。
配置文件一旦存在，加载时完全以文件内容为准，不再引用这里的默认值。

例外：``PluginParameterSpec`` / ``PLUGIN_PARAMETER_TABLE`` /
``default_plugin_parameters()`` 是每次 reload 都消费的运行时常量
（``service._ensure_plugin_parameters`` 用它幂等建参），并非只在首次播种时使用。

与 expression/defaults.py 同构：所有默认工厂统一放在本模块，命名一律 default_*()，
每次调用返回新实例，避免共享可变状态。
"""

from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionBinding,
    SemanticActionProfile,
)

from .plugin_parameters import PLUGIN_PARAMETER_TABLE, PluginParameterSpec

# 语义动作 ↔ 插件参数 的单一事实源：建参清单与默认绑定都从 PLUGIN_PARAMETER_TABLE 派生，
# 避免名字在 service 与 defaults 之间漂移。语义 Spec 的 min/max/neutral 与
# 此处 minimum/maximum/default 保持一致，使 adapter 线性映射退化为恒等。


def default_plugin_parameters() -> tuple[PluginParameterSpec, ...]:
    """返回 LiveStudio 需在 VTS 侧确保存在的插件自定义参数"""

    return tuple(spec for _, spec in PLUGIN_PARAMETER_TABLE)


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
        # VTS 内置参数（出现在 default_parameters，无需 _ensure_plugin_parameters 建参；
        # 范围由 _refresh_parameter_specs 从 VTS 实测同步）
        SemanticActionBinding(
            action=SemanticAction.MOUTH_CHEEK_PUFF,
            platform_params=["CheekPuff"],
        ),
        SemanticActionBinding(
            action=SemanticAction.MOUTH_TONGUE_OUT,
            platform_params=["TongueOut"],
        ),
        *(
            SemanticActionBinding(action=action, platform_params=[spec.name])
            for action, spec in PLUGIN_PARAMETER_TABLE
        ),
    ]
    return SemanticActionProfile(
        bindings=bindings,
    )

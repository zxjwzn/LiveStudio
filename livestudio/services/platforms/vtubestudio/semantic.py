"""VTube Studio 通用动作的默认对应关系"""

from __future__ import annotations

from collections.abc import Iterable

from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticAction,
    SemanticActionAdapter,
    SemanticActionBinding,
    SemanticActionProfile,
)


class VTubeStudioSemanticAdapter(SemanticActionAdapter):
    """把通用动作换成 VTube Studio 里的跟踪参数"""

    def __init__(
        self,
        profile: SemanticActionProfile,
        parameter_specs: Iterable[PlatformParameterSpec]
        | dict[str, PlatformParameterSpec]
        | None = None,
    ) -> None:
        super().__init__(
            profile,
            parameter_specs=_merge_parameter_specs(parameter_specs),
        )


def default_vtube_studio_parameter_specs() -> tuple[PlatformParameterSpec, ...]:
    """返回 VTube Studio 常用跟踪参数的范围"""

    return (
        PlatformParameterSpec(
            name="FacePositionX",
            minimum=-15.0,
            maximum=15.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="FacePositionY",
            minimum=-15.0,
            maximum=15.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="FacePositionZ",
            minimum=-10.0,
            maximum=10.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="FaceAngleX",
            minimum=-30.0,
            maximum=30.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="FaceAngleY",
            minimum=-30.0,
            maximum=30.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="FaceAngleZ",
            minimum=-90.0,
            maximum=90.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="MouthSmile",
            minimum=0.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="MouthOpen",
            minimum=0.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="Brows",
            minimum=0.0,
            maximum=1.0,
            neutral=0.5,
            default=0.5,
        ),
        PlatformParameterSpec(
            name="BrowLeftY",
            minimum=0.0,
            maximum=1.0,
            neutral=0.5,
            default=0.5,
        ),
        PlatformParameterSpec(
            name="BrowRightY",
            minimum=0.0,
            maximum=1.0,
            neutral=0.5,
            default=0.5,
        ),
        PlatformParameterSpec(
            name="EyeOpenLeft",
            minimum=0.0,
            maximum=1.0,
            neutral=0.75,
            default=1.0,
        ),
        PlatformParameterSpec(
            name="EyeOpenRight",
            minimum=0.0,
            maximum=1.0,
            neutral=0.75,
            default=1.0,
        ),
        PlatformParameterSpec(
            name="EyeLeftX",
            minimum=-1.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="EyeLeftY",
            minimum=-1.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="EyeRightX",
            minimum=-1.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="EyeRightY",
            minimum=-1.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="MousePositionX",
            minimum=-1.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="MousePositionY",
            minimum=-1.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="MouthX",
            minimum=-1.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
    )


def _merge_parameter_specs(
    parameter_specs: Iterable[PlatformParameterSpec]
    | dict[str, PlatformParameterSpec]
    | None,
) -> dict[str, PlatformParameterSpec]:
    merged = {spec.name: spec for spec in default_vtube_studio_parameter_specs()}
    if parameter_specs is None:
        return merged
    overrides = (
        parameter_specs.values()
        if isinstance(parameter_specs, dict)
        else parameter_specs
    )
    merged.update({spec.name: spec for spec in overrides})
    return merged


def default_vtube_studio_semantic_bindings() -> tuple[SemanticActionBinding, ...]:
    """返回常见 VTube Studio 模型的默认动作对应关系"""

    return (
        SemanticActionBinding(
            action=SemanticAction.BROW_HEIGHT.value,
            platform_params=["BrowLeftY", "BrowRightY"],
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_OPEN.value,
            platform_params=["EyeOpenLeft", "EyeOpenRight"],
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_GAZE_X.value,
            platform_params=["EyeLeftX", "EyeRightX"],
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_GAZE_Y.value,
            platform_params=["EyeLeftY", "EyeRightY"],
        ),
        SemanticActionBinding(
            action=SemanticAction.MOUTH_OPEN.value,
            platform_params=["MouthOpen"],
        ),
        SemanticActionBinding(
            action=SemanticAction.MOUTH_SMILE.value,
            platform_params=["MouthSmile"],
        ),
        SemanticActionBinding(
            action=SemanticAction.MOUTH_FROWN.value,
            platform_params=["MouthSmile"],
            enabled=False,
        ),
        SemanticActionBinding(
            action=SemanticAction.HEAD_YAW.value,
            platform_params=["FaceAngleX"],
        ),
        SemanticActionBinding(
            action=SemanticAction.HEAD_PITCH.value,
            platform_params=["FaceAngleY"],
        ),
        SemanticActionBinding(
            action=SemanticAction.HEAD_ROLL.value,
            platform_params=["FaceAngleZ"],
        ),
    )


def default_vtube_studio_semantic_profile(
    *,
    model_id: str = "",
    model_name: str = "",
) -> SemanticActionProfile:
    return SemanticActionProfile(
        model_id=model_id,
        model_name=model_name,
        bindings={
            binding.action: binding
            for binding in default_vtube_studio_semantic_bindings()
        },
    )

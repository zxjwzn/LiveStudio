"""VTube Studio semantic action adapter defaults."""

from __future__ import annotations

from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticAction,
    SemanticActionAdapter,
    SemanticActionBinding,
    SemanticActionProfile,
)


class VTubeStudioSemanticAdapter(SemanticActionAdapter):
    """Resolve semantic actions to VTube Studio tracking parameters."""

    def __init__(self, profile: SemanticActionProfile) -> None:
        super().__init__(
            profile,
            parameter_specs=default_vtube_studio_parameter_specs(),
        )


def default_vtube_studio_parameter_specs() -> tuple[PlatformParameterSpec, ...]:
    """Return documented VTube Studio tracking parameter ranges used by adapters."""

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
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="BrowLeftY",
            minimum=0.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
        ),
        PlatformParameterSpec(
            name="BrowRightY",
            minimum=0.0,
            maximum=1.0,
            neutral=0.0,
            default=0.0,
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


def default_vtube_studio_semantic_bindings() -> tuple[SemanticActionBinding, ...]:
    """Return default semantic action mappings for common VTube Studio models."""

    return (
        SemanticActionBinding(
            action=SemanticAction.BROW_RAISE.value,
            platform_params=["BrowLeftY", "BrowRightY"],
        ),
        SemanticActionBinding(
            action=SemanticAction.BROW_LOWER.value,
            platform_params=["BrowLeftY", "BrowRightY"],
            enabled=False,
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_CLOSE.value,
            platform_params=["EyeOpenLeft", "EyeOpenRight"],
            inverted=True,
        ),
        SemanticActionBinding(
            action=SemanticAction.EYE_WIDEN.value,
            platform_params=["EyeOpenLeft", "EyeOpenRight"],
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


def refreshed_vtube_studio_semantic_binding_ids() -> tuple[str, ...]:
    """Return default bindings that should replace unsafe legacy no-op mappings."""

    return (
        SemanticAction.BROW_LOWER.value,
        SemanticAction.MOUTH_FROWN.value,
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

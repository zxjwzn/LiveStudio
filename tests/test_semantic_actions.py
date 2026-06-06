"""测试通用动作转换工具"""

from __future__ import annotations

import pytest

from livestudio.services.platforms.vtubestudio import (
    VTubeStudioSemanticAdapter,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionTarget,
    SemanticTweenRequest,
)


def test_vtube_semantic_adapter_maps_eye_open_state() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    closed = adapter.resolve(SemanticActionTarget(SemanticAction.EYE_OPEN.value, 0.0))
    neutral = adapter.resolve(SemanticActionTarget(SemanticAction.EYE_OPEN.value, 0.75))
    open_ = adapter.resolve(SemanticActionTarget(SemanticAction.EYE_OPEN.value, 1.0))

    assert {state.name for state in closed} == {"EyeOpenLeft", "EyeOpenRight"}
    assert [state.value for state in closed] == [pytest.approx(0.0)] * 2
    assert [state.value for state in neutral] == [pytest.approx(0.75)] * 2
    assert [state.value for state in open_] == [pytest.approx(1.0)] * 2
    assert {state.start_value for state in closed} == {0.75}


def test_vtube_semantic_adapter_maps_head_roll_to_platform_range() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    resolved = adapter.resolve(
        SemanticActionTarget(SemanticAction.HEAD_ROLL.value, 0.5),
    )

    assert len(resolved) == 1
    assert resolved[0].name == "FaceAngleZ"
    assert resolved[0].value == pytest.approx(45.0)


def test_vtube_semantic_adapter_maps_brow_height_state() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())
    target = SemanticActionTarget

    lowered = adapter.resolve(target(SemanticAction.BROW_HEIGHT.value, 0.0))
    neutral = adapter.resolve(target(SemanticAction.BROW_HEIGHT.value, 0.5))
    raised = adapter.resolve(target(SemanticAction.BROW_HEIGHT.value, 1.0))

    assert {state.name for state in lowered} == {"BrowLeftY", "BrowRightY"}
    assert [state.value for state in lowered] == [pytest.approx(0.0)] * 2
    assert [state.value for state in neutral] == [pytest.approx(0.5)] * 2
    assert [state.value for state in raised] == [pytest.approx(1.0)] * 2


def test_vtube_semantic_adapter_maps_eye_gaze_axes() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())
    target = SemanticActionTarget

    gaze_x = adapter.resolve(target(SemanticAction.EYE_GAZE_X.value, -0.6))
    gaze_y = adapter.resolve(target(SemanticAction.EYE_GAZE_Y.value, 0.4))

    assert {state.name for state in gaze_x} == {"EyeLeftX", "EyeRightX"}
    assert [state.value for state in gaze_x] == [pytest.approx(-0.6)] * 2
    assert {state.name for state in gaze_y} == {"EyeLeftY", "EyeRightY"}
    assert [state.value for state in gaze_y] == [pytest.approx(0.4)] * 2


def test_semantic_support_score_is_binary_coverage() -> None:
    profile = default_vtube_studio_semantic_profile()

    assert (
        profile.support_score(
            (SemanticActionTarget(SemanticAction.EYE_OPEN.value, 1.0),),
        )
        == 1.0
    )
    assert (
        profile.support_score(
            (SemanticActionTarget("unknown.action", 1.0),),
        )
        == 0.0
    )


def test_semantic_binding_rejects_unknown_fields() -> None:
    from pydantic import ValidationError

    from livestudio.services.semantic_actions import SemanticActionBinding

    with pytest.raises(ValidationError):
        SemanticActionBinding.model_validate(
            {
                "action": SemanticAction.EYE_OPEN.value,
                "platform_params": ["EyeOpenLeft"],
                "unknown": True,
            },
        )


def test_semantic_adapter_merges_colliding_platform_parameters() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    requests = adapter.resolve_request(
        SemanticTweenRequest(
            targets=(
                SemanticActionTarget(SemanticAction.EYE_OPEN.value, 0.5),
                SemanticActionTarget(SemanticAction.EYE_OPEN.value, 1.0),
            ),
            duration=0.1,
            easing="linear",
        ),
        current_states={},
    )

    by_name = {request.parameter_name: request for request in requests}
    assert set(by_name) == {"EyeOpenLeft", "EyeOpenRight"}
    assert by_name["EyeOpenLeft"].end_value == pytest.approx(0.75)


def test_semantic_adapter_maps_semantic_start_values_to_platform_range() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    requests = adapter.resolve_request(
        SemanticTweenRequest(
            targets=(
                SemanticActionTarget(
                    SemanticAction.HEAD_ROLL.value,
                    0.5,
                    start_value=-0.5,
                ),
            ),
            duration=0.1,
            easing="linear",
        ),
        current_states={},
    )

    assert requests[0].parameter_name == "FaceAngleZ"
    assert requests[0].start_value == pytest.approx(-45.0)
    assert requests[0].end_value == pytest.approx(45.0)


def test_semantic_adapter_normalizes_platform_values_to_semantic_range() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    eye_open = adapter.normalize_platform_values(
        SemanticAction.EYE_OPEN.value,
        {"EyeOpenLeft": 0.5, "EyeOpenRight": 1.0},
    )
    head_roll = adapter.normalize_platform_values(
        SemanticAction.HEAD_ROLL.value,
        {"FaceAngleZ": -45.0},
    )

    assert eye_open is not None
    assert eye_open.value == pytest.approx(0.75)
    assert eye_open.platform_values == {"EyeOpenLeft": 0.5, "EyeOpenRight": 1.0}
    assert head_roll is not None
    assert head_roll.value == pytest.approx(-0.5)


def test_semantic_adapter_reports_bound_platform_parameters() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    assert adapter.platform_parameters_for(SemanticAction.MOUTH_SMILE.value) == (
        "MouthSmile",
    )
    assert adapter.platform_parameters_for("unknown.action") == ()

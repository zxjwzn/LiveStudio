"""测试语义动作转换工具"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import pytest
from pydantic import ValidationError

from livestudio.services.platforms.vtubestudio import default_vtube_studio_semantic_profile
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticAction,
    SemanticActionAdapter,
    SemanticActionBinding,
    SemanticActionProfile,
    SemanticTweenRequest,
)
from livestudio.services.tween import ControlledParameterState, ParameterTweenEngine


def _parameter_specs() -> list[PlatformParameterSpec]:
    return [
        PlatformParameterSpec(name="FaceAngleZ", minimum=-90.0, maximum=90.0),
        PlatformParameterSpec(name="MouthOpen", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="MouthSmile", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="Brows", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="BrowLeftY", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="BrowRightY", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="EyeLeftX", minimum=-1.0, maximum=1.0),
        PlatformParameterSpec(name="EyeRightX", minimum=-1.0, maximum=1.0),
        PlatformParameterSpec(name="EyeOpenLeft", minimum=0.0, maximum=1.0),
        PlatformParameterSpec(name="EyeOpenRight", minimum=0.0, maximum=1.0),
    ]


class _TweenRecorder:
    def __init__(self) -> None:
        self.states: list[ControlledParameterState] = []

    async def __call__(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        _ = mode
        self.states.extend(states)


def _default_adapter() -> SemanticActionAdapter:
    recorder = _TweenRecorder()
    engine = ParameterTweenEngine(recorder)
    return SemanticActionAdapter(
        default_vtube_studio_semantic_profile(),
        parameter_specs=_parameter_specs(),
        engine=engine,
    )


def test_semantic_adapter_maps_action_to_platform_range() -> None:
    adapter = _default_adapter()

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.HEAD_ROLL.value,
                end_value=0.5,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    assert len(requests) == 1
    assert requests[0].parameter_name == "FaceAngleZ"
    assert requests[0].end_value == pytest.approx(45.0)


def test_semantic_adapter_maps_mouth_open_zero_to_platform_minimum() -> None:
    adapter = _default_adapter()

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.MOUTH_OPEN.value,
                end_value=0.0,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    assert len(requests) == 1
    assert requests[0].parameter_name == "MouthOpen"
    assert requests[0].end_value == pytest.approx(0.0)


def test_semantic_adapter_maps_separate_brow_height_bindings() -> None:
    adapter = _default_adapter()

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.BROW_HEIGHT_LEFT.value,
                end_value=0.7,
                duration=0.1,
                easing="linear",
            ),
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.BROW_HEIGHT_RIGHT.value,
                end_value=0.3,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    by_name = {request.parameter_name: request for request in requests}
    assert set(by_name) == {"BrowLeftY", "BrowRightY"}
    assert by_name["BrowLeftY"].end_value == pytest.approx(0.7)
    assert by_name["BrowRightY"].end_value == pytest.approx(0.3)


def test_semantic_adapter_can_bind_common_brow_height_to_shared_platform_parameter() -> None:
    recorder = _TweenRecorder()
    engine = ParameterTweenEngine(recorder)
    adapter = SemanticActionAdapter(
        SemanticActionProfile(
            bindings=[
                SemanticActionBinding(
                    action=SemanticAction.BROW_HEIGHT,
                    platform_params=["Brows"],
                ),
            ],
        ),
        parameter_specs=_parameter_specs(),
        engine=engine,
    )

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.BROW_HEIGHT.value,
                end_value=0.8,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    assert requests[0].parameter_name == "Brows"
    assert requests[0].end_value == pytest.approx(0.8)


def test_semantic_adapter_maps_multiple_bound_parameters() -> None:
    adapter = _default_adapter()

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.EYE_GAZE_X.value,
                end_value=-0.6,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    assert {request.parameter_name for request in requests} == {"EyeLeftX", "EyeRightX"}
    assert [request.end_value for request in requests] == [pytest.approx(-0.6)] * 2


def test_semantic_adapter_maps_separate_eye_open_bindings() -> None:
    adapter = _default_adapter()

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.EYE_OPEN_LEFT.value,
                end_value=0.25,
                duration=0.1,
                easing="linear",
            ),
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.EYE_OPEN_RIGHT.value,
                end_value=0.75,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    by_name = {request.parameter_name: request for request in requests}
    assert set(by_name) == {"EyeOpenLeft", "EyeOpenRight"}
    assert by_name["EyeOpenLeft"].end_value == pytest.approx(0.25)
    assert by_name["EyeOpenRight"].end_value == pytest.approx(0.75)


def test_semantic_adapter_clamps_semantic_value_before_mapping() -> None:
    adapter = _default_adapter()

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.HEAD_ROLL.value,
                end_value=2.0,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    assert requests[0].end_value == pytest.approx(90.0)


def test_semantic_adapter_maps_semantic_start_values_to_platform_range() -> None:
    adapter = _default_adapter()

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.HEAD_ROLL.value,
                end_value=0.5,
                start_value=-0.5,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    assert requests[0].parameter_name == "FaceAngleZ"
    assert requests[0].start_value == pytest.approx(-45.0)
    assert requests[0].end_value == pytest.approx(45.0)


def test_semantic_adapter_uses_neutral_start_value_without_controlled_state() -> None:
    adapter = _default_adapter()

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.EYE_OPEN.value,
                end_value=0.3,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    assert {request.parameter_name for request in requests} == {"EyeOpenLeft", "EyeOpenRight"}
    assert [request.start_value for request in requests] == [pytest.approx(0.8), pytest.approx(0.8)]


def test_semantic_adapter_keeps_engine_start_value_with_controlled_state() -> None:
    adapter = _default_adapter()
    adapter._engine._controlled_params["EyeOpenLeft"] = ControlledParameterState(  # noqa: SLF001
        name="EyeOpenLeft",
        value=0.4,
        mode="set",
    )

    requests = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.EYE_OPEN.value,
                end_value=0.3,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    by_name = {request.parameter_name: request for request in requests}
    assert by_name["EyeOpenLeft"].start_value is None
    assert by_name["EyeOpenRight"].start_value == pytest.approx(0.8)


def test_semantic_adapter_query_returns_instant_value() -> None:
    adapter = _default_adapter()
    adapter._engine._controlled_params["FaceAngleZ"] = ControlledParameterState(  # noqa: SLF001
        name="FaceAngleZ",
        value=-45.0,
        mode="set",
    )

    assert adapter.query(SemanticAction.HEAD_ROLL.value) == pytest.approx(-0.5)


def test_semantic_adapter_query_returns_first_bound_value_when_values_differ() -> None:
    adapter = _default_adapter()
    adapter._engine._controlled_params["EyeOpenLeft"] = ControlledParameterState(  # noqa: SLF001
        name="EyeOpenLeft",
        value=0.2,
        mode="set",
    )
    adapter._engine._controlled_params["EyeOpenRight"] = ControlledParameterState(  # noqa: SLF001
        name="EyeOpenRight",
        value=0.8,
        mode="set",
    )

    assert adapter.query(SemanticAction.EYE_OPEN.value) == pytest.approx(0.2)


def test_semantic_support_score_uses_profile_bindings() -> None:
    profile = default_vtube_studio_semantic_profile()

    class Target:
        def __init__(self, action: str, weight: float = 1.0) -> None:
            self.action = action
            self.weight = weight

    assert profile.support_score((Target(SemanticAction.EYE_OPEN.value),)) == 1.0
    assert profile.support_score((Target("unknown.action"),)) == 0.0


def test_semantic_binding_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SemanticActionBinding.model_validate(
            {
                "action": SemanticAction.EYE_OPEN.value,
                "platform_params": ["EyeOpenLeft"],
                "unknown": True,
            },
        )


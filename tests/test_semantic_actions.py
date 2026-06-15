"""测试语义动作转换工具"""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import ValidationError

from livestudio.services.platforms.vtubestudio import (
    default_vtube_studio_parameter_specs,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.semantic_actions import SemanticActionAdapter
from livestudio.services.semantic_actions.models import (
    SemanticAction,
    SemanticTweenRequest,
)
from livestudio.services.tween import ControlledParameterState, ParameterTweenEngine


class _TweenRecorder:
    def __init__(self) -> None:
        self.states: list[ControlledParameterState] = []

    async def __call__(
        self,
        states: list[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        _ = mode
        self.states.extend(states)


def _default_adapter() -> SemanticActionAdapter:
    recorder = _TweenRecorder()
    engine = ParameterTweenEngine(recorder)
    return SemanticActionAdapter(
        default_vtube_studio_semantic_profile(),
        parameter_specs=default_vtube_studio_parameter_specs(),
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


def test_semantic_adapter_query_returns_instant_value() -> None:
    adapter = _default_adapter()
    adapter._engine._controlled_params["FaceAngleZ"] = ControlledParameterState(  # noqa: SLF001
        name="FaceAngleZ",
        value=-45.0,
        mode="set",
    )

    assert adapter.query(SemanticAction.HEAD_ROLL.value) == pytest.approx(-0.5)


def test_semantic_support_score_uses_profile_bindings() -> None:
    profile = default_vtube_studio_semantic_profile()

    class Target:
        def __init__(self, action: str, weight: float = 1.0) -> None:
            self.action = action
            self.weight = weight

    assert profile.support_score((Target(SemanticAction.EYE_OPEN.value),)) == 1.0
    assert profile.support_score((Target("unknown.action"),)) == 0.0


def test_semantic_binding_rejects_unknown_fields() -> None:
    from livestudio.services.semantic_actions.models import SemanticActionBinding

    with pytest.raises(ValidationError):
        SemanticActionBinding.model_validate(
            {
                "action": SemanticAction.EYE_OPEN.value,
                "platform_params": ["EyeOpenLeft"],
                "unknown": True,
            },
        )

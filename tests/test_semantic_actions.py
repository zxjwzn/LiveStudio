"""Semantic action adapter tests."""

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


def test_vtube_semantic_adapter_closes_both_eyes() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    resolved = adapter.resolve(
        SemanticActionTarget(SemanticAction.EYE_CLOSE.value, 1.0),
    )

    assert {state.name for state in resolved} == {"EyeOpenLeft", "EyeOpenRight"}
    assert [state.value for state in resolved] == [pytest.approx(0.0)] * 2
    assert {state.start_value for state in resolved} == {0.75}


def test_vtube_semantic_adapter_maps_head_roll_to_platform_range() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    resolved = adapter.resolve(
        SemanticActionTarget(SemanticAction.HEAD_ROLL.value, 0.5),
    )

    assert len(resolved) == 1
    assert resolved[0].name == "FaceAngleZ"
    assert resolved[0].value == pytest.approx(45.0)


def test_vtube_default_adapter_does_not_fake_unsupported_brow_lower() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    brow_lower = adapter.resolve(
        SemanticActionTarget(SemanticAction.BROW_LOWER.value, 1.0),
    )
    mouth_frown = adapter.resolve(
        SemanticActionTarget(SemanticAction.MOUTH_FROWN.value, 1.0),
    )

    assert brow_lower == []
    assert mouth_frown == []


def test_semantic_support_score_is_binary_coverage() -> None:
    profile = default_vtube_studio_semantic_profile()

    assert (
        profile.support_score(
            (SemanticActionTarget(SemanticAction.EYE_CLOSE.value, 1.0),),
        )
        == 1.0
    )
    assert (
        profile.support_score(
            (SemanticActionTarget(SemanticAction.BROW_LOWER.value, 1.0),),
        )
        == 0.0
    )


def test_semantic_adapter_merges_colliding_platform_parameters() -> None:
    adapter = VTubeStudioSemanticAdapter(default_vtube_studio_semantic_profile())

    requests = adapter.resolve_request(
        SemanticTweenRequest(
            targets=(
                SemanticActionTarget(SemanticAction.EYE_CLOSE.value, 0.4),
                SemanticActionTarget(SemanticAction.EYE_WIDEN.value, 0.2),
            ),
            duration=0.1,
            easing="linear",
        ),
        current_states={},
    )

    by_name = {request.parameter_name: request for request in requests}
    assert set(by_name) == {"EyeOpenLeft", "EyeOpenRight"}
    assert by_name["EyeOpenLeft"].end_value == pytest.approx(0.625)


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

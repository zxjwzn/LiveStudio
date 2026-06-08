"""测试表情系统能不能正常工作"""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, Protocol, cast

import pytest
import yaml

from tests.conftest import _SenderRecorder
from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.services.expressions import (
    BUILTIN_EXPRESSION_UNITS,
    EmotionKind,
    EmotionRequest,
    ExpressionCombinationRule,
    ExpressionIntent,
    ExpressionRegion,
    ExpressionSelector,
    ExpressionService,
    ExpressionTarget,
    ExpressionUnit,
)
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    VTubeStudioSemanticAdapter,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.platforms.vtubestudio.config import VTubeStudioModelConfig
from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionTarget,
)
from livestudio.services.semantic_actions.adapter import PlatformParameterSpec
from livestudio.tween import (
    ControlledParameterState,
    ParameterTweenEngine,
    TweenRequest,
)


class _SemanticVtsPlatform(VTubeStudio):
    def __init__(
        self,
        *,
        tween: ParameterTweenEngine,
        adapter: VTubeStudioSemanticAdapter,
    ) -> None:
        self._tween = tween
        self._semantic_adapter = adapter

    @property
    def tween(self) -> ParameterTweenEngine:
        return self._tween

    @property
    def semantic_adapter(self) -> VTubeStudioSemanticAdapter | None:
        return self._semantic_adapter

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class _ParameterValueRequestDataLike(Protocol):
    name: str


class _ParameterValueRequestLike(Protocol):
    data: _ParameterValueRequestDataLike


class _ParameterValueResponseDataLike(Protocol):
    value: float


class _ParameterValueResponseLike(Protocol):
    data: _ParameterValueResponseDataLike


class _ParameterValueClient:
    def __init__(self, values: dict[str, float]) -> None:
        self.values = values
        self.requested: list[str] = []

    async def get_parameter_value(
        self,
        request: _ParameterValueRequestLike,
    ) -> _ParameterValueResponseLike:
        name = request.data.name
        self.requested.append(name)
        return cast(
            _ParameterValueResponseLike,
            type(
                "Response",
                (),
                {"data": type("Data", (), {"value": self.values[name]})()},
            )(),
        )


def test_anger_selects_tense_mouth_with_semantic_tags() -> None:
    profile = default_vtube_studio_semantic_profile()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        profile,
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.ANGER: 1.0},
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert any(unit.id == "mouth_press" for unit in selected.units)
    assert {"anger", "tense"}.issubset(selected.semantic_tags)
    assert "friendly" not in selected.semantic_tags
    target_values = {target.action: target.value for target in selected.targets}
    assert 0.0 <= target_values[SemanticAction.MOUTH_SMILE.value] <= 1.0


def test_mouth_corner_and_mouth_open_states_are_separate_units() -> None:
    units_by_id = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}

    mouth_corner_up_actions = {
        target.action for target in units_by_id["mouth_corner_up"].targets
    }
    mouth_slight_open_actions = {
        target.action for target in units_by_id["mouth_slight_open"].targets
    }

    assert mouth_corner_up_actions == {SemanticAction.MOUTH_SMILE.value}
    assert mouth_slight_open_actions == {SemanticAction.MOUTH_OPEN.value}


def test_mouth_press_can_mix_with_mouth_corner_up_on_same_parameters() -> None:
    units_by_id = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    targets = selector.merge_unit_targets(
        (units_by_id["mouth_corner_up"], units_by_id["mouth_press"]),
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0, EmotionKind.ANGER: 0.4},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    target_values = {target.action: target.value for target in targets}
    assert {SemanticAction.MOUTH_SMILE.value, SemanticAction.MOUTH_OPEN.value} <= set(
        target_values,
    )
    assert 0.0 < target_values[SemanticAction.MOUTH_SMILE.value] < 1.0
    assert target_values[SemanticAction.MOUTH_OPEN.value] <= 0.04


def test_eye_units_are_closed_narrow_and_open_states() -> None:
    units_by_id = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}

    assert {"eye_closed", "eye_narrow", "eye_open"}.issubset(units_by_id)
    assert units_by_id["eye_closed"].conflicts == frozenset(
        {"eye_narrow", "eye_open"},
    )
    assert units_by_id["eye_narrow"].conflicts == frozenset(
        {"eye_closed", "eye_open"},
    )
    assert units_by_id["eye_open"].conflicts == frozenset(
        {"eye_closed", "eye_narrow"},
    )


def test_pure_joy_can_select_mouth_slight_open_as_optional_unit() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    target_actions = {target.action for target in selected.targets}

    assert "mouth_corner_up" in unit_ids
    assert "mouth_slight_open" in unit_ids
    assert SemanticAction.MOUTH_OPEN.value in target_actions


def test_single_strong_unit_can_be_selected_without_full_region_coverage() -> None:
    strong_unit = ExpressionUnit(
        id="single_smile",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(ExpressionTarget(SemanticAction.MOUTH_SMILE.value, value=0.8),),
        action_tags=frozenset({"smile", "mouth_smile"}),
        naturalness=1.0,
    )
    weak_unit = ExpressionUnit(
        id="weak_brow",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(ExpressionTarget(SemanticAction.BROW_HEIGHT.value, value=0.55),),
        action_tags=frozenset({"brow_raise", "subtle"}),
        naturalness=0.2,
    )
    selector = ExpressionSelector(
        (strong_unit, weak_unit),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        intents=(
            ExpressionIntent(
                id="single_smile_intent",
                emotion_profile={EmotionKind.JOY: 1.0},
                required_units=frozenset({"single_smile"}),
                optional_units={"weak_brow": 0.1},
                output_tags=frozenset({"single_smile_intent"}),
            ),
        ),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intent="single_smile_intent",
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert [unit.id for unit in selected.units] == ["single_smile"]
    assert set(selected.units_by_region) == {ExpressionRegion.MOUTH}
    assert {"joy", "smile"}.issubset(selected.semantic_tags)


def test_expression_rules_exclude_inconsistent_emotion_tags() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.ANGER: 1.0},
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert "friendly" not in selected.semantic_tags
    assert "anger" in selected.semantic_tags


def test_combination_rules_can_block_otherwise_compatible_units() -> None:
    smile = ExpressionUnit(
        id="smile",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(ExpressionTarget(SemanticAction.MOUTH_SMILE.value, value=0.8),),
        action_tags=frozenset({"smile", "mouth_smile"}),
    )
    wide = ExpressionUnit(
        id="wide",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(ExpressionTarget(SemanticAction.EYE_OPEN.value, value=0.95),),
        action_tags=frozenset({"eye_wide", "wide"}),
    )
    selector = ExpressionSelector(
        (smile, wide),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        intents=(
            ExpressionIntent(
                id="smile_with_optional_wide",
                emotion_profile={EmotionKind.JOY: 1.0},
                required_units=frozenset({"smile"}),
                optional_units={"wide": 1.0},
                output_tags=frozenset({"smile_with_optional_wide"}),
            ),
        ),
        combination_rules=(
            ExpressionCombinationRule(
                id="smile_blocks_wide",
                require_tags=frozenset({"smile", "wide"}),
                penalty=float("inf"),
            ),
        ),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intent="smile_with_optional_wide",
            randomness=0.0,
        ),
    )

    assert not {"smile", "wide"}.issubset(selected.semantic_tags)


def test_selector_expresses_sadness_with_low_mouth_smile() -> None:
    profile = default_vtube_studio_semantic_profile()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        profile,
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.SADNESS: 1.0},
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert any(unit.id == "mouth_corner_down" for unit in selected.units)
    assert {"sadness", "restrained"}.issubset(selected.semantic_tags)
    target_values = {target.action: target.value for target in selected.targets}
    assert target_values[SemanticAction.MOUTH_SMILE.value] <= 0.08


def test_selector_accepts_partial_emotion_weight() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.SADNESS: 0.5},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    assert selected.units
    assert "sadness" in selected.semantic_tags


def test_emotion_request_accepts_independent_emotion_vector_values() -> None:
    request = EmotionRequest(
        emotions={EmotionKind.JOY: 0.8, EmotionKind.ANGER: 0.3},
    )

    assert request.emotions == {EmotionKind.JOY: 0.8, EmotionKind.ANGER: 0.3}


def test_selector_builds_mischievous_downcast_white_eye_smile() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 0.65, EmotionKind.ANGER: 0.35},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    assert {
        "mouth_corner_up",
        "head_down_mischievous",
        "gaze_up_white",
    }.issubset(unit_ids)
    assert {"sinister", "white_eye", "head_down", "smile"}.issubset(
        selected.semantic_tags,
    )
    target_values = {target.action: target.value for target in selected.targets}
    assert target_values[SemanticAction.HEAD_PITCH.value] < 0.0
    assert target_values[SemanticAction.EYE_GAZE_Y.value] > 0.0
    assert target_values[SemanticAction.MOUTH_SMILE.value] > 0.35


def test_selector_uses_explicit_expression_intent_template() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intent="sinister_smile",
            intensity=1.0,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    assert selected.intent_id == "sinister_smile"
    assert {
        "mouth_corner_up",
        "head_down_mischievous",
        "gaze_up_white",
    }.issubset(unit_ids)
    assert "sinister_smile" in selected.semantic_tags


def test_selector_auto_selects_expression_intent_from_emotion_signature() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 0.65, EmotionKind.ANGER: 0.35},
            intensity=0.8,
            randomness=0.0,
        ),
    )

    assert selected.intent_id == "sinister_smile"
    assert "sinister_smile" in selected.semantic_tags


def test_selector_builds_bitter_smile_from_joy_sadness_vector() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0, EmotionKind.SADNESS: 0.5},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    assert selected.intent_id == "bitter_smile"
    assert {"mouth_corner_up", "brow_knit"}.issubset(unit_ids)
    assert "bitter_smile" in selected.semantic_tags


def test_emotion_vector_energy_controls_expression_strength() -> None:
    low_energy_selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )
    high_energy_selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    low_energy = low_energy_selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 0.45, EmotionKind.ANGER: 0.35},
            intensity=1.0,
            randomness=0.0,
        ),
    )
    high_energy = high_energy_selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 0.9, EmotionKind.ANGER: 0.7},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    low_targets = {target.action: target.value for target in low_energy.targets}
    high_targets = {target.action: target.value for target in high_energy.targets}

    assert low_energy.intent_id == "sinister_smile"
    assert high_energy.intent_id == "sinister_smile"
    assert high_energy.expression_strength > low_energy.expression_strength
    assert high_targets[SemanticAction.MOUTH_SMILE.value] > low_targets[SemanticAction.MOUTH_SMILE.value]


def test_sinister_smile_variants_follow_emotion_deviation() -> None:
    playful_selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )
    threatening_selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    playful = playful_selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 0.7, EmotionKind.ANGER: 0.3},
            intensity=1.0,
            randomness=0.0,
        ),
    )
    threatening = threatening_selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 0.7, EmotionKind.ANGER: 0.7},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    playful_targets = {target.action: target.value for target in playful.targets}
    threatening_targets = {
        target.action: target.value for target in threatening.targets
    }

    assert playful.intent_id == "sinister_smile"
    assert threatening.intent_id == "sinister_smile"
    assert "mischief_high" in playful.semantic_tags
    assert "threat_high" in threatening.semantic_tags
    assert (
        threatening_targets[SemanticAction.EYE_GAZE_Y.value]
        > playful_targets[SemanticAction.EYE_GAZE_Y.value]
    )
    assert (
        threatening_targets[SemanticAction.HEAD_PITCH.value]
        < playful_targets[SemanticAction.HEAD_PITCH.value]
    )
    assert (
        playful_targets[SemanticAction.MOUTH_SMILE.value]
        > threatening_targets[SemanticAction.MOUTH_SMILE.value]
    )


def test_selector_rejects_unknown_expression_intent() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    with pytest.raises(ValueError, match="unknown expression intent"):
        selector.select(
            EmotionRequest(
                emotions={EmotionKind.JOY: 1.0},
                intent="missing_intent",
                intensity=0.8,
                randomness=0.0,
            ),
        )


def test_selector_randomizes_range_targets_within_semantic_range() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(2),
    )

    stable = selector.preview(
        EmotionRequest(
            emotions={EmotionKind.SADNESS: 1.0},
            intensity=0.7,
            randomness=0.0,
            value_jitter=0.0,
        ),
    )
    jittered = selector.preview(
        EmotionRequest(
            emotions={EmotionKind.SADNESS: 1.0},
            intensity=0.7,
            randomness=1.0,
            value_jitter=0.1,
        ),
    )

    stable_values = {target.action: target.value for target in stable.targets}
    jittered_values = {target.action: target.value for target in jittered.targets}
    assert stable_values != jittered_values
    assert all(-1.0 <= value <= 1.0 for value in jittered_values.values())


def test_history_avoidance_penalizes_repeated_expression() -> None:
    profile = default_vtube_studio_semantic_profile()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        profile,
        rng=random.Random(1),
    )
    request = EmotionRequest(
        emotions={EmotionKind.JOY: 1.0},
        intensity=0.7,
        randomness=0.0,
        history_avoidance=1.0,
    )

    first = selector.select(request)
    second = selector.preview(request)

    assert second.score < first.score


def test_selector_builds_semantically_tagged_expression_for_emotion() -> None:
    profile = default_vtube_studio_semantic_profile()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        profile,
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert selected.score > 0
    assert {"joy", "smile"}.issubset(selected.semantic_tags)
    assert selected.units_by_region
    assert any(
        target.action == SemanticAction.MOUTH_SMILE.value for target in selected.targets
    )


async def test_expression_service_applies_semantic_tweens() -> None:
    sender = _SenderRecorder()
    tween = ParameterTweenEngine(sender)
    profile = default_vtube_studio_semantic_profile()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        profile,
        rng=random.Random(1),
    )
    service = ExpressionService(
        platform=_SemanticVtsPlatform(
            tween=tween,
            adapter=VTubeStudioSemanticAdapter(profile),
        ),
        selector=selector,
    )

    selected = await service.express(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert selected.targets
    assert sender.calls
    sent_names = {state.name for _, states in sender.calls for state in states}
    assert "MouthSmile" in sent_names


async def test_expression_service_uses_current_controlled_values_as_start_values() -> (
    None
):
    captured_start_values: dict[str, float | None] = {}

    async def sender(
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        _ = states, mode

    class _CapturingTween(ParameterTweenEngine):
        capture_requests = False

        async def tween(self, request: TweenRequest) -> None:
            if not self.capture_requests:
                await super().tween(request)
                return
            captured_start_values[request.parameter_name] = request.start_value

    tween = _CapturingTween(sender)
    await tween.tween(
        TweenRequest(
            parameter_name="EyeOpenLeft",
            end_value=0.42,
            duration=0.0,
            easing="linear",
        ),
    )
    await tween.tween(
        TweenRequest(
            parameter_name="EyeOpenRight",
            end_value=0.43,
            duration=0.0,
            easing="linear",
        ),
    )
    captured_start_values.clear()
    tween.capture_requests = True

    profile = default_vtube_studio_semantic_profile()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        profile,
        rng=random.Random(1),
    )
    service = ExpressionService(
        platform=_SemanticVtsPlatform(
            tween=tween,
            adapter=VTubeStudioSemanticAdapter(profile),
        ),
        selector=selector,
    )

    await service.express(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert captured_start_values["EyeOpenLeft"] == 0.42
    assert captured_start_values["EyeOpenRight"] == 0.43


async def test_expression_service_falls_back_to_platform_neutral_start_values() -> None:
    captured_start_values: dict[str, float | None] = {}

    async def sender(
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        _ = states, mode

    class _CapturingTween(ParameterTweenEngine):
        async def tween(self, request: TweenRequest) -> None:
            captured_start_values[request.parameter_name] = request.start_value

    profile = default_vtube_studio_semantic_profile()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        profile,
        rng=random.Random(1),
    )
    service = ExpressionService(
        platform=_SemanticVtsPlatform(
            tween=_CapturingTween(sender),
            adapter=VTubeStudioSemanticAdapter(profile),
        ),
        selector=selector,
    )

    await service.express(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert captured_start_values["EyeOpenLeft"] == 0.75
    assert captured_start_values["EyeOpenRight"] == 0.75


def test_vtube_model_config_contains_semantic_profile_defaults() -> None:
    config = VTubeStudioModelConfig()
    config.model.model_id = "model-id"
    config.model.model_name = "Model"

    changed = config.ensure_semantic_profile_defaults()

    assert changed
    assert config.semantic_profile.model_id == "model-id"
    assert config.semantic_profile.model_name == "Model"
    assert SemanticAction.MOUTH_OPEN.value in config.semantic_profile.bindings


def test_vtube_model_config_contains_parameter_spec_defaults() -> None:
    config = VTubeStudioModelConfig(parameter_specs=[])

    changed = config.ensure_parameter_spec_defaults()

    assert changed
    assert any(spec.name == "MouthOpen" for spec in config.parameter_specs)


def test_vtube_semantic_adapter_uses_model_parameter_specs() -> None:
    profile = default_vtube_studio_semantic_profile()
    adapter = VTubeStudioSemanticAdapter(
        profile,
        [
            PlatformParameterSpec(
                name="EyeOpenLeft",
                minimum=10.0,
                maximum=20.0,
                neutral=15.0,
                default=20.0,
            ),
            PlatformParameterSpec(
                name="EyeOpenRight",
                minimum=30.0,
                maximum=50.0,
                neutral=40.0,
                default=50.0,
            ),
        ],
    )

    resolved = adapter.resolve(
        SemanticActionTarget(SemanticAction.EYE_OPEN.value, 0.75),
    )

    by_name = {state.name: state for state in resolved}
    assert by_name["EyeOpenLeft"].value == 15.0
    assert by_name["EyeOpenRight"].value == 40.0


async def test_vtube_platform_queries_real_values_as_semantic_state() -> None:
    profile = default_vtube_studio_semantic_profile()
    platform = VTubeStudio()
    client = _ParameterValueClient({"EyeOpenLeft": 0.5, "EyeOpenRight": 1.0})
    platform._client = cast(  # noqa: SLF001
        VTubeStudioClient,
        client,
    )
    platform._semantic_adapter = VTubeStudioSemanticAdapter(profile)  # noqa: SLF001

    state = await platform.get_semantic_value(SemanticAction.EYE_OPEN.value)

    assert state is not None
    assert state.value == 0.75
    assert client.requested == ["EyeOpenLeft", "EyeOpenRight"]


async def test_reload_model_config_persists_backfilled_semantic_profile(
    tmp_path: Path,
) -> None:
    platform = VTubeStudio()
    platform.config.model_config_dir = str(tmp_path)
    config_path = tmp_path / "Model_model-id.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "model": {
                    "platform_name": "",
                    "model_id": "",
                    "model_name": "",
                },
                "controllers": {},
                "expressions": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = await platform.reload_model_config("model-id", "Model")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config.semantic_profile.model_id == "model-id"
    assert raw["semantic_profile"]["model_id"] == "model-id"
    assert "parameter_specs" not in raw["semantic_profile"]
    assert SemanticAction.MOUTH_OPEN.value in raw["semantic_profile"]["bindings"]


async def test_reload_model_config_uses_configs_relative_model_dir(
    tmp_path: Path,
) -> None:
    platform = VTubeStudio()
    platform.config.model_config_dir = "models/vtubestudio"
    original_model_config_dir = platform.config.model_config_dir
    platform.config.model_config_dir = str(tmp_path / original_model_config_dir)

    config = await platform.reload_model_config("model-id", "Model")

    expected_path = tmp_path / "models" / "vtubestudio" / "Model_model-id.yaml"
    assert expected_path.exists()
    assert config.semantic_profile.model_id == "model-id"

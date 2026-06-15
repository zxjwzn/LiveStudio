"""测试表情系统能不能正常工作"""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, Protocol, cast

import pytest
import yaml

from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.services.expressions import (
    BUILTIN_COMBINATION_RULES,
    BUILTIN_EXPRESSION_UNITS,
    EmotionKind,
    EmotionRequest,
    ExpressionCombinationRule,
    ExpressionIntent,
    ExpressionIntentOptional,
    ExpressionRegion,
    ExpressionSelector,
    ExpressionService,
    ExpressionTarget,
    ExpressionUnit,
)
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    default_vtube_studio_parameter_specs,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.platforms.vtubestudio.config import VTubeStudioModelConfig
from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionAdapter,
)
from livestudio.services.semantic_actions.models import PlatformParameterSpec, SemanticTweenRequest
from livestudio.services.tween import (
    ControlledParameterState,
    ParameterTweenEngine,
    TweenRequest,
)
from tests.conftest import _SenderRecorder


def _default_vts_adapter(profile, tween: ParameterTweenEngine) -> SemanticActionAdapter:
    return SemanticActionAdapter(
        profile,
        parameter_specs=default_vtube_studio_parameter_specs(),
        engine=tween,
    )


class _SemanticVtsPlatform(VTubeStudio):
    def __init__(
        self,
        *,
        tween: ParameterTweenEngine,
        adapter: SemanticActionAdapter,
    ) -> None:
        self._tween = tween
        self._semantic_adapter = adapter

    @property
    def tween(self) -> ParameterTweenEngine:
        return self._tween

    @property
    def semantic_adapter(self) -> SemanticActionAdapter | None:
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

    assert any(unit.id == "抿嘴" for unit in selected.units)
    assert selected.semantic_tags == frozenset({"anger", "愤怒"})
    target_values = {target.action: target.value for target in selected.targets}
    assert 0.0 <= target_values[SemanticAction.MOUTH_SMILE.value] <= 1.0


def test_mouth_corner_and_mouth_open_states_are_separate_units() -> None:
    units_by_id = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}

    嘴角上扬_actions = {target.action for target in units_by_id["嘴角上扬"].targets}
    嘴巴微张_actions = {target.action for target in units_by_id["嘴巴微张"].targets}

    assert 嘴角上扬_actions == {SemanticAction.MOUTH_SMILE.value}
    assert 嘴巴微张_actions == {SemanticAction.MOUTH_OPEN.value}


def test_mouth_position_units_are_available_and_conflicted_by_axis() -> None:
    units_by_id = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}
    exclusive_groups = {rule.any_of_unit_ids for rule in BUILTIN_COMBINATION_RULES}

    assert {"嘴部左移", "嘴部右移", "嘴部上移", "嘴部下移"}.issubset(units_by_id)
    assert {target.action for target in units_by_id["嘴部左移"].targets} == {
        SemanticAction.MOUTH_X.value,
    }
    assert {target.action for target in units_by_id["嘴部上移"].targets} == {
        SemanticAction.MOUTH_Y.value,
    }
    assert frozenset({"嘴部左移", "嘴部右移"}) in exclusive_groups
    assert frozenset({"嘴部上移", "嘴部下移"}) in exclusive_groups


def test_抿嘴_can_mix_with_嘴角上扬_on_same_parameters() -> None:
    units_by_id = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    targets = selector.merge_unit_targets(
        (units_by_id["嘴角上扬"], units_by_id["抿嘴"]),
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


def test_eye_conflicts_are_defined_by_combination_rules() -> None:
    exclusive_groups = {rule.any_of_unit_ids for rule in BUILTIN_COMBINATION_RULES}

    assert frozenset({"闭眼", "眯眼", "睁眼"}) in exclusive_groups


def test_head_conflicts_are_defined_by_combination_rules() -> None:
    units_by_id = {unit.id: unit for unit in BUILTIN_EXPRESSION_UNITS}
    exclusive_groups = {rule.any_of_unit_ids for rule in BUILTIN_COMBINATION_RULES}

    assert {"抬头", "低头", "左歪头", "右歪头", "左转头", "右转头"}.issubset(
        units_by_id,
    )
    assert frozenset({"抬头", "低头"}) in exclusive_groups
    assert frozenset({"左歪头", "右歪头"}) in exclusive_groups
    assert frozenset({"左转头", "右转头"}) in exclusive_groups


def test_mutually_exclusive_optional_units_are_chosen_with_randomness() -> None:
    selected_sides: set[str] = set()

    for seed in range(20):
        selector = ExpressionSelector(
            BUILTIN_EXPRESSION_UNITS,
            default_vtube_studio_semantic_profile(),
            rng=random.Random(seed),
        )

        selected = selector.select(
            EmotionRequest(
                emotions={EmotionKind.JOY: 1.0},
                intensity=1.0,
                randomness=1.0,
                max_units=4,
            ),
        )
        unit_ids = {unit.id for unit in selected.units}

        assert not {"左歪头", "右歪头"}.issubset(unit_ids)
        selected_sides.update(unit_ids.intersection({"左歪头", "右歪头"}))

    assert selected_sides == {"左歪头", "右歪头"}


def test_喜悦_can_select_嘴巴微张_as_optional_unit() -> None:
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

    assert "嘴角上扬" in unit_ids
    assert "嘴巴微张" in unit_ids
    assert SemanticAction.MOUTH_OPEN.value in target_actions


def test_single_strong_unit_can_be_selected_without_full_region_coverage() -> None:
    strong_unit = ExpressionUnit(
        id="single_smile",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(ExpressionTarget(SemanticAction.MOUTH_SMILE.value, value=0.8),),
        naturalness=1.0,
    )
    weak_unit = ExpressionUnit(
        id="weak_brow",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(ExpressionTarget(SemanticAction.BROW_HEIGHT.value, value=0.55),),
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
                optional_units=(
                    ExpressionIntentOptional(
                        id="weak_brow",
                        units=frozenset({"weak_brow"}),
                        weight=0.1,
                    ),
                ),
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
    assert selected.semantic_tags == frozenset({"joy", "single_smile_intent"})


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

    assert selected.semantic_tags == frozenset({"anger", "愤怒"})


def test_combination_rules_can_block_otherwise_compatible_units() -> None:
    smile = ExpressionUnit(
        id="smile",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(ExpressionTarget(SemanticAction.MOUTH_SMILE.value, value=0.8),),
    )
    wide = ExpressionUnit(
        id="wide",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(ExpressionTarget(SemanticAction.EYE_OPEN.value, value=0.95),),
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
                optional_units=(
                    ExpressionIntentOptional(
                        id="wide",
                        units=frozenset({"wide"}),
                        weight=1.0,
                    ),
                ),
            ),
        ),
        combination_rules=(
            ExpressionCombinationRule(
                id="smile_blocks_wide",
                required_unit_ids=frozenset({"smile", "wide"}),
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

    assert [unit.id for unit in selected.units] == ["smile"]


def test_optional_unit_group_adds_multiple_units_together() -> None:
    smile = ExpressionUnit(
        id="smile",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(ExpressionTarget(SemanticAction.MOUTH_SMILE.value, value=0.8),),
    )
    tilt = ExpressionUnit(
        id="tilt",
        regions=frozenset({ExpressionRegion.HEAD}),
        targets=(ExpressionTarget(SemanticAction.HEAD_ROLL.value, value=0.2),),
    )
    glance = ExpressionUnit(
        id="glance",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(ExpressionTarget(SemanticAction.EYE_GAZE_X.value, value=0.4),),
    )
    selector = ExpressionSelector(
        (smile, tilt, glance),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        intents=(
            ExpressionIntent(
                id="grouped_optional",
                emotion_profile={EmotionKind.JOY: 1.0},
                required_units=frozenset({"smile"}),
                optional_units=(
                    ExpressionIntentOptional(
                        id="tilt_with_glance",
                        units=frozenset({"tilt", "glance"}),
                        weight=1.0,
                    ),
                ),
            ),
        ),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intent="grouped_optional",
            randomness=0.0,
            max_units=3,
        ),
    )

    assert {unit.id for unit in selected.units} == {"smile", "tilt", "glance"}


def test_optional_unit_group_is_skipped_when_it_exceeds_max_units() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        intents=(
            ExpressionIntent(
                id="group_exceeds_max_units",
                emotion_profile={EmotionKind.JOY: 1.0},
                required_units=frozenset({"嘴角上扬"}),
                optional_units=(
                    ExpressionIntentOptional(
                        id="head_pair",
                        units=frozenset({"左歪头", "眼睛左看"}),
                        weight=1.0,
                    ),
                ),
            ),
        ),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intent="group_exceeds_max_units",
            randomness=0.0,
            max_units=2,
        ),
    )

    assert "嘴角上扬" in {unit.id for unit in selected.units}
    assert not {"左歪头", "眼睛左看"}.issubset(
        {unit.id for unit in selected.units},
    )


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

    assert any(unit.id == "嘴角下压" for unit in selected.units)
    assert selected.semantic_tags == frozenset({"sadness", "悲伤"})
    target_values = {target.action: target.value for target in selected.targets}
    assert target_values[SemanticAction.MOUTH_SMILE.value] <= 0.4


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


def test_selector_builds_戏谑_downcast_white_eye_smile() -> None:
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
        "嘴角上扬",
        "低头",
        "眼睛上看",
    }.issubset(unit_ids)
    assert selected.semantic_tags == frozenset({"joy", "阴险笑"})
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
            intent="阴险笑",
            intensity=1.0,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    assert selected.intent_id == "阴险笑"
    assert {
        "嘴角上扬",
        "低头",
        "眼睛上看",
    }.issubset(unit_ids)
    assert "阴险笑" in selected.semantic_tags


def test_anger_can_trigger_glare_optional_group_with_default_max_units() -> None:
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

    unit_ids = {unit.id for unit in selected.units}
    assert {"抿嘴", "皱眉", "眯眼", "低头", "眼睛上看"}.issubset(unit_ids)


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

    assert selected.intent_id == "阴险笑"
    assert "阴险笑" in selected.semantic_tags


def test_range_target_stays_inside_unit_range_after_intensity_scaling() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 0.6, EmotionKind.ANGER: 0.4},
            intensity=0.7,
            randomness=0.0,
        ),
    )

    assert any(unit.id == "眯眼" for unit in selected.units)
    target_values = {target.action: target.value for target in selected.targets}
    assert target_values[SemanticAction.EYE_OPEN.value] <= 0.4


def test_selector_builds_苦笑_from_joy_sadness_vector() -> None:
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
    assert selected.intent_id == "苦笑"
    assert {"嘴角上扬", "皱眉"}.issubset(unit_ids)
    assert "苦笑" in selected.semantic_tags


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

    assert low_energy.intent_id == "阴险笑"
    assert high_energy.intent_id == "阴险笑"
    assert high_energy.expression_strength > low_energy.expression_strength


def test_阴险笑_variants_follow_emotion_deviation() -> None:
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

    threatening_targets = {
        target.action: target.value for target in threatening.targets
    }

    assert playful.intent_id == "阴险笑"
    assert threatening.intent_id == "阴险笑"
    assert playful.semantic_tags == frozenset({"joy", "阴险笑"})
    assert threatening.semantic_tags == frozenset({"joy", "阴险笑"})
    assert threatening_targets[SemanticAction.EYE_GAZE_Y.value] <= 1.0
    assert threatening_targets[SemanticAction.HEAD_PITCH.value] >= -0.7
    assert threatening_targets[SemanticAction.EYE_OPEN.value] <= 0.4


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
                intent="不存在的意图",
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
    assert selected.semantic_tags == frozenset({"joy", "喜悦"})
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
            adapter=_default_vts_adapter(profile, tween),
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

        async def tween(self, requests: list[TweenRequest]) -> None:
            if not self.capture_requests:
                await super().tween(requests)
                return
            for request in requests:
                captured_start_values[request.parameter_name] = request.start_value

    tween = _CapturingTween(sender)
    await tween.tween(
        [
            TweenRequest(
            parameter_name="EyeOpenLeft",
            end_value=0.42,
            duration=0.0,
            easing="linear",
        ),
        ],
    )
    await tween.tween(
        [
            TweenRequest(
            parameter_name="EyeOpenRight",
            end_value=0.43,
            duration=0.0,
            easing="linear",
        ),
        ],
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
            adapter=_default_vts_adapter(profile, tween),
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

    assert captured_start_values["EyeOpenLeft"] is None
    assert captured_start_values["EyeOpenRight"] is None


async def test_expression_service_falls_back_to_platform_neutral_start_values() -> None:
    captured_start_values: dict[str, float | None] = {}

    async def sender(
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        _ = states, mode

    class _CapturingTween(ParameterTweenEngine):
        async def tween(self, requests: list[TweenRequest]) -> None:
            for request in requests:
                captured_start_values[request.parameter_name] = request.start_value

    profile = default_vtube_studio_semantic_profile()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        profile,
        rng=random.Random(1),
    )
    tween = _CapturingTween(sender)
    service = ExpressionService(
        platform=_SemanticVtsPlatform(
            tween=tween,
            adapter=_default_vts_adapter(profile, tween),
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

    assert captured_start_values["EyeOpenLeft"] is None
    assert captured_start_values["EyeOpenRight"] is None


def test_vtube_model_config_contains_semantic_profile_defaults() -> None:
    config = VTubeStudioModelConfig()
    config.init_defaults()

    assert SemanticAction.MOUTH_OPEN.value in {
        binding.action for binding in config.semantic_profile.bindings
    }


def test_vtube_semantic_adapter_uses_model_parameter_specs() -> None:
    profile = default_vtube_studio_semantic_profile()
    specs = default_vtube_studio_parameter_specs()
    specs_by_name = {spec.name: spec for spec in specs}
    specs_by_name["EyeOpenLeft"] = PlatformParameterSpec(
        name="EyeOpenLeft",
        minimum=10.0,
        maximum=20.0,
    )
    specs_by_name["EyeOpenRight"] = PlatformParameterSpec(
        name="EyeOpenRight",
        minimum=30.0,
        maximum=50.0,
    )
    adapter = SemanticActionAdapter(
        profile,
        parameter_specs=list(specs_by_name.values()),
        engine=ParameterTweenEngine(_SenderRecorder()),
    )

    resolved = adapter.to_tween_requests(
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.EYE_OPEN.value,
                end_value=0.75,
                duration=0.1,
                easing="linear",
            ),
        ],
    )

    by_name = {request.parameter_name: request for request in resolved}
    assert by_name["EyeOpenLeft"].end_value == 17.5
    assert by_name["EyeOpenRight"].end_value == 45.0


async def test_vtube_platform_queries_real_values_as_semantic_state() -> None:
    profile = default_vtube_studio_semantic_profile()
    platform = VTubeStudio()
    client = _ParameterValueClient({"EyeOpenLeft": 0.5, "EyeOpenRight": 1.0})
    platform._client = cast(  # noqa: SLF001
        VTubeStudioClient,
        client,
    )
    platform._semantic_adapter = _default_vts_adapter(profile, platform.tween)  # noqa: SLF001
    platform.tween._controlled_params["EyeOpenLeft"] = ControlledParameterState(  # noqa: SLF001
        name="EyeOpenLeft",
        value=0.5,
        mode="set",
    )
    platform.tween._controlled_params["EyeOpenRight"] = ControlledParameterState(  # noqa: SLF001
        name="EyeOpenRight",
        value=1.0,
        mode="set",
    )

    value = await platform.get_semantic_value(SemanticAction.EYE_OPEN.value)

    assert value == 0.75
    assert client.requested == []


async def test_reload_model_config_creates_default_model_config(
    tmp_path: Path,
) -> None:
    platform = VTubeStudio()
    platform.config.model_config_dir = str(tmp_path)
    config_path = tmp_path / "Model_model.yaml"

    config = await platform.reload_model_config("model-id", "Model")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config.model.model_id == "model-id"
    assert "model_id" not in raw["semantic_profile"]
    assert "model_name" not in raw["semantic_profile"]
    assert "parameter_specs" not in raw["semantic_profile"]
    assert SemanticAction.MOUTH_OPEN.value in {
        binding["action"] for binding in raw["semantic_profile"]["bindings"]
    }


async def test_reload_model_config_uses_configs_relative_model_dir(
    tmp_path: Path,
) -> None:
    platform = VTubeStudio()
    platform.config.model_config_dir = "models/vtubestudio"
    original_model_config_dir = platform.config.model_config_dir
    platform.config.model_config_dir = str(tmp_path / original_model_config_dir)

    config = await platform.reload_model_config("model-id", "Model")

    expected_path = tmp_path / "models" / "vtubestudio" / "Model_model.yaml"
    assert expected_path.exists()
    assert config.model.model_id == "model-id"

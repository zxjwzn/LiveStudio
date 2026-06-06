"""测试表情系统能不能正常工作"""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml

from livestudio.services.expressions import (
    BUILTIN_EXPRESSION_UNITS,
    EmotionKind,
    EmotionProfile,
    EmotionRequest,
    ExpressionCombinationRule,
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


class _SenderRecorder:
    def __init__(self) -> None:
        self.calls: list[
            tuple[Literal["set", "add"], list[ControlledParameterState]]
        ] = []

    async def __call__(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        self.calls.append((mode, list(states)))


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


class _ParameterValueClient:
    def __init__(self, values: dict[str, float]) -> None:
        self.values = values
        self.requested: list[str] = []

    async def get_parameter_value(self, request: object) -> object:
        name = request.data.name
        self.requested.append(name)
        return type(
            "Response",
            (),
            {"data": type("Data", (), {"value": self.values[name]})()},
        )()


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


def test_single_strong_unit_can_be_selected_without_full_region_coverage() -> None:
    strong_unit = ExpressionUnit(
        id="single_smile",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(ExpressionTarget(SemanticAction.MOUTH_SMILE.value, value=0.8),),
        emotions={
            EmotionKind.JOY: EmotionProfile(
                weight=1.0,
                tags=frozenset({"joy", "smile"}),
                intensity=0.7,
            ),
        },
        naturalness=1.0,
    )
    weak_unit = ExpressionUnit(
        id="weak_brow",
        regions=frozenset({ExpressionRegion.BROW}),
        targets=(ExpressionTarget(SemanticAction.BROW_HEIGHT.value, value=0.55),),
        emotions={
            EmotionKind.JOY: EmotionProfile(
                weight=0.1,
                tags=frozenset({"joy", "subtle"}),
                intensity=0.7,
            ),
        },
        naturalness=0.2,
    )
    selector = ExpressionSelector(
        (strong_unit, weak_unit),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
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
        emotions={
            EmotionKind.JOY: EmotionProfile(
                weight=1.0,
                tags=frozenset({"joy", "smile"}),
            ),
        },
    )
    wide = ExpressionUnit(
        id="wide",
        regions=frozenset({ExpressionRegion.EYE}),
        targets=(ExpressionTarget(SemanticAction.EYE_OPEN.value, value=0.95),),
        emotions={
            EmotionKind.JOY: EmotionProfile(
                weight=0.9,
                tags=frozenset({"joy", "wide"}),
            ),
        },
    )
    selector = ExpressionSelector(
        (smile, wide),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
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

    assert any(unit.id == "mouth_down" for unit in selected.units)
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


def test_selector_builds_mischievous_downcast_white_eye_smile() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0, EmotionKind.ANGER: 0.5},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    assert {
        "mouth_sinister_smile",
        "head_down_mischievous",
        "gaze_up_white",
    }.issubset(unit_ids)
    assert {"sinister", "white_eye", "head_down", "smile"}.issubset(
        selected.semantic_tags,
    )
    target_values = {target.action: target.value for target in selected.targets}
    assert target_values[SemanticAction.HEAD_PITCH.value] < 0.0
    assert target_values[SemanticAction.EYE_GAZE_Y.value] > 0.0
    assert target_values[SemanticAction.MOUTH_SMILE.value] > 0.5


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
    platform._client = _ParameterValueClient(  # noqa: SLF001
        {"EyeOpenLeft": 0.5, "EyeOpenRight": 1.0},
    )
    platform._semantic_adapter = VTubeStudioSemanticAdapter(profile)  # noqa: SLF001

    state = await platform.get_semantic_value(SemanticAction.EYE_OPEN.value)

    assert state is not None
    assert state.value == 0.75
    assert platform.client.requested == ["EyeOpenLeft", "EyeOpenRight"]


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

"""Expression system tests."""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import yaml

from livestudio.services.expressions import (
    BUILTIN_EXPRESSION_UNITS,
    EmotionKind,
    EmotionRequest,
    ExpressionRegion,
    ExpressionSelector,
    ExpressionService,
    ExpressionUnit,
)
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    VTubeStudioSemanticAdapter,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.platforms.vtubestudio.config import VTubeStudioModelConfig
from livestudio.services.semantic_actions import SemanticAction, SemanticActionTarget
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


def test_anger_selects_tense_mouth_without_smile_action() -> None:
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

    assert selected.units[ExpressionRegion.MOUTH].id == "mouth_anger_tense"
    assert selected.units[ExpressionRegion.MOUTH].tags.isdisjoint({"friendly"})
    assert all(
        target.action != SemanticAction.MOUTH_SMILE.value for target in selected.targets
    )


def test_hard_conflicts_exclude_otherwise_best_combo() -> None:
    units = (
        ExpressionUnit(
            id="brow_tense",
            region=ExpressionRegion.BROW,
            targets=(),
            emotions={EmotionKind.ANGER: 1.0},
            intensity=0.7,
            tags=frozenset({"tense"}),
            conflicts=frozenset({"friendly"}),
        ),
        ExpressionUnit(
            id="brow_fallback",
            region=ExpressionRegion.BROW,
            targets=(),
            emotions={EmotionKind.ANGER: 0.4},
            intensity=0.7,
        ),
        ExpressionUnit(
            id="eye_friendly",
            region=ExpressionRegion.EYE,
            targets=(),
            emotions={EmotionKind.ANGER: 1.0},
            intensity=0.7,
            tags=frozenset({"friendly"}),
        ),
        ExpressionUnit(
            id="mouth_none",
            region=ExpressionRegion.MOUTH,
            targets=(),
            emotions={EmotionKind.ANGER: 1.0},
            intensity=0.7,
        ),
        ExpressionUnit(
            id="head_none",
            region=ExpressionRegion.HEAD,
            targets=(),
            emotions={EmotionKind.ANGER: 1.0},
            intensity=0.7,
        ),
    )
    selector = ExpressionSelector(
        units,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        combination_rules=(),
    )

    selected = selector.select(
        EmotionRequest(emotions={EmotionKind.ANGER: 1.0}, randomness=0.0),
    )

    assert selected.units[ExpressionRegion.BROW].id == "brow_fallback"


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

    assert all("friendly" not in unit.tags for unit in selected.units.values())


def test_selector_jitters_targets_within_semantic_range() -> None:
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        default_vtube_studio_semantic_profile(),
        rng=random.Random(2),
    )

    stable = selector.preview(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=0.7,
            randomness=1.0,
            value_jitter=0.0,
        ),
    )
    jittered = selector.preview(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
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


def test_selector_builds_full_expression_for_emotion() -> None:
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

    assert set(selected.units) == {
        ExpressionRegion.BROW,
        ExpressionRegion.EYE,
        ExpressionRegion.MOUTH,
        ExpressionRegion.HEAD,
    }
    assert selected.score > 0
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
    config.model.id = "model-id"
    config.model.name = "Model"

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
                "model": {"id": "", "name": ""},
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

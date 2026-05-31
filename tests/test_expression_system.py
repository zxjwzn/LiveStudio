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
)
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    VTubeStudioSemanticAdapter,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.platforms.vtubestudio.config import VTubeStudioModelConfig
from livestudio.services.semantic_actions import SemanticAction
from livestudio.services.semantic_actions.adapter import SemanticActionAdapter
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

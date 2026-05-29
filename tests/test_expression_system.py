"""Expression system tests."""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import pytest
import yaml

from livestudio.services.expressions import (
    BUILTIN_EXPRESSION_UNITS,
    CalibrationProfile,
    EmotionKind,
    EmotionRequest,
    ExpressionRegion,
    ExpressionSelector,
    ExpressionService,
    SemanticParameter,
    default_vtube_studio_calibrations,
)
from livestudio.services.platforms.vtubestudio import VTubeStudio
from livestudio.services.platforms.vtubestudio.config import VTubeStudioModelConfig
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


def test_default_calibration_resolves_semantic_parameter() -> None:
    calibration = CalibrationProfile.with_defaults(model_id="model", model_name="name")

    states = calibration.resolve(SemanticParameter.MOUTH_SMILE.value, 0.5)

    assert len(states) == 1
    state = states[0]
    assert state.name == "MouthSmile"
    assert state.value == pytest.approx(0.5)
    assert calibration.supports(SemanticParameter.MOUTH_SMILE.value)


def test_default_eye_calibration_drives_both_eyes() -> None:
    calibration = CalibrationProfile.with_defaults()

    states = calibration.resolve(SemanticParameter.EYE_SQUINT.value, 0.35)

    assert {state.name for state in states} == {"EyeOpenLeft", "EyeOpenRight"}
    assert {round(state.value, 3) for state in states} == {0.557}
    assert {state.start_value for state in states} == {0.75}


def test_default_calibration_matches_documented_vts_tracking_ranges() -> None:
    ranges = _load_documented_vts_ranges()

    for calibration in default_vtube_studio_calibrations():
        for vts_param in calibration.vts_params:
            assert vts_param in ranges
            minimum, maximum, _default = ranges[vts_param]
            assert minimum <= calibration.negative_limit <= maximum
            assert minimum <= calibration.neutral <= maximum
            assert minimum <= calibration.positive_limit <= maximum

    head_roll = CalibrationProfile.with_defaults().parameters[
        SemanticParameter.HEAD_ROLL.value
    ]
    assert head_roll.negative_limit == -90.0
    assert head_roll.positive_limit == 90.0


def test_anger_selects_tense_mouth_without_smile_or_unknown_vts_params() -> None:
    calibration = CalibrationProfile.with_defaults()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        calibration,
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

    resolved = [
        state
        for target in selected.targets
        for state in calibration.resolve(target.semantic_param, target.value)
    ]
    documented_params = set(_load_documented_vts_ranges())
    assert {state.name for state in resolved} <= documented_params
    assert all(state.name != "MouthSmile" or state.value <= 0.0 for state in resolved)
    assert all(state.name != "MouthPucker" for state in resolved)


def test_selector_builds_full_expression_for_emotion() -> None:
    calibration = CalibrationProfile.with_defaults()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        calibration,
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
        target.semantic_param == SemanticParameter.MOUTH_SMILE.value
        for target in selected.targets
    )


async def test_expression_service_applies_calibrated_tweens() -> None:
    sender = _SenderRecorder()
    tween = ParameterTweenEngine(sender)
    calibration = CalibrationProfile.with_defaults()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        calibration,
        rng=random.Random(1),
    )
    service = ExpressionService(
        tween=tween,
        calibration=calibration,
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


async def test_expression_service_uses_current_controlled_values_as_start_values() -> None:
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

    calibration = CalibrationProfile.with_defaults()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        calibration,
        rng=random.Random(1),
    )
    service = ExpressionService(
        tween=tween,
        calibration=calibration,
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


async def test_expression_service_falls_back_to_neutral_start_values() -> None:
    captured_start_values: dict[str, float | None] = {}

    async def sender(
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        _ = states, mode

    class _CapturingTween(ParameterTweenEngine):
        async def tween(self, request: TweenRequest) -> None:
            captured_start_values[request.parameter_name] = request.start_value

    calibration = CalibrationProfile.with_defaults()
    selector = ExpressionSelector(
        BUILTIN_EXPRESSION_UNITS,
        calibration,
        rng=random.Random(1),
    )
    service = ExpressionService(
        tween=_CapturingTween(sender),
        calibration=calibration,
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


def test_vtube_model_config_contains_expression_calibration_defaults() -> None:
    config = VTubeStudioModelConfig()
    config.model.id = "model-id"
    config.model.name = "Model"

    changed = config.ensure_expression_calibration_defaults()

    assert changed
    assert config.expression_calibration.model_id == "model-id"
    assert config.expression_calibration.model_name == "Model"
    assert (
        SemanticParameter.MOUTH_OPEN.value in config.expression_calibration.parameters
    )


def test_vtube_model_config_refreshes_stale_expression_calibration() -> None:
    config = VTubeStudioModelConfig()
    stale_pucker = config.expression_calibration.parameters[
        SemanticParameter.MOUTH_OPEN.value
    ].model_copy(update={"semantic_param": SemanticParameter.MOUTH_PUCKER.value})
    config.expression_calibration.parameters[
        SemanticParameter.MOUTH_FROWN.value
    ].positive_limit = 1.0
    config.expression_calibration.parameters[SemanticParameter.MOUTH_PUCKER.value] = (
        stale_pucker
    )
    config.expression_calibration.parameters[
        SemanticParameter.HEAD_ROLL.value
    ].positive_limit = 30.0
    config.expression_calibration.parameters[
        SemanticParameter.HEAD_ROLL.value
    ].negative_limit = -30.0

    changed = config.ensure_expression_calibration_defaults()

    assert changed
    assert (
        SemanticParameter.MOUTH_PUCKER.value
        not in config.expression_calibration.parameters
    )
    assert (
        config.expression_calibration.parameters[
            SemanticParameter.MOUTH_FROWN.value
        ].positive_limit
        == 0.0
    )
    assert (
        config.expression_calibration.parameters[
            SemanticParameter.HEAD_ROLL.value
        ].positive_limit
        == 90.0
    )


def test_vtube_model_config_backfills_missing_expression_calibration() -> None:
    config = VTubeStudioModelConfig.model_validate(
        {
            "model": {"id": "model-id", "name": "Model"},
            "controllers": {},
            "expressions": [],
        },
    )

    changed = config.ensure_expression_calibration_defaults()

    assert changed
    assert config.expression_calibration.model_id == "model-id"
    assert config.expression_calibration.model_name == "Model"
    assert (
        SemanticParameter.MOUTH_SMILE.value in config.expression_calibration.parameters
    )


def test_vtube_model_config_backfills_empty_profile() -> None:
    empty_config = VTubeStudioModelConfig.model_validate(
        {
            "expression_calibration": {},
        },
    )
    assert (
        SemanticParameter.MOUTH_OPEN.value
        in empty_config.expression_calibration.parameters
    )


async def test_reload_model_config_persists_backfilled_profile(tmp_path: Path) -> None:
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
    assert config.expression_calibration.model_id == "model-id"
    assert raw["expression_calibration"]["model_id"] == "model-id"
    assert (
        SemanticParameter.MOUTH_OPEN.value
        in raw["expression_calibration"]["parameters"]
    )


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
    assert config.expression_calibration.model_id == "model-id"


def _load_documented_vts_ranges() -> dict[str, tuple[float, float, float]]:
    path = Path(__file__).resolve().parents[1] / "docs" / "vts默认参数.txt"
    ranges: dict[str, tuple[float, float, float]] = {}
    current_name: str | None = None
    current_maximum: float | None = None
    current_minimum: float | None = None
    current_default: float | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("参数: "):
            current_name = line.split(": ", 1)[1]
            current_maximum = None
            current_minimum = None
            current_default = None
            continue
        if line.startswith("最大值: "):
            current_maximum = float(line.split(": ", 1)[1])
            continue
        if line.startswith("最小值: "):
            current_minimum = float(line.split(": ", 1)[1])
            continue
        if line.startswith("默认值: "):
            current_default = float(line.split(": ", 1)[1])
            continue
        if line.startswith("---------------") and current_name is not None:
            assert current_minimum is not None
            assert current_maximum is not None
            assert current_default is not None
            ranges[current_name] = (
                current_minimum,
                current_maximum,
                current_default,
            )
            current_name = None

    return ranges

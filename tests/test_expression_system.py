"""测试 AU 表情解算系统能不能正常工作"""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path
from typing import Literal, Protocol, cast

import pytest
import yaml

from livestudio.clients.vtube_studio.client import VTubeStudioClient
from livestudio.services.expressions import (
    BUILTIN_EXPRESSION_UNITS,
    EmotionKind,
    EmotionRequest,
    ExpressionCombinationRule,
    ExpressionRegion,
    ExpressionRuleConfig,
    ExpressionRuleKind,
    ExpressionSelector,
    ExpressionService,
    ExpressionTarget,
    ExpressionTargetConfig,
    ExpressionUnit,
    ExpressionUnitConfig,
    default_expression_profile,
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
from tests.conftest import _SenderRecorder


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


def _selector(*, rng_seed: int = 1) -> ExpressionSelector:
    expression_profile = default_expression_profile()
    return ExpressionSelector(
        expression_profile.to_units(),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(rng_seed),
        combination_rules=expression_profile.to_rules(),
    )


def test_anger_selects_correlated_au_directly() -> None:
    selected = _selector().select(
        EmotionRequest(
            emotions={EmotionKind.ANGER: 1.0},
            intensity=0.8,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    assert {"皱眉", "抿嘴", "眯眼"}.issubset(unit_ids)
    assert "嘴角上扬" not in unit_ids
    assert selected.emotion == EmotionKind.ANGER
    assert selected.semantic_tags == frozenset({"anger", "au_solver"})


def test_joy_selects_smile_and_suppresses_negative_correlations() -> None:
    selected = _selector().select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=0.8,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    assert "嘴角上扬" in unit_ids
    assert "嘴角下压" not in unit_ids
    assert "抿嘴" not in unit_ids


def test_emotion_request_only_accepts_one_positive_emotion() -> None:
    with pytest.raises(ValueError, match="只能包含一个正向情绪强度"):
        EmotionRequest(
            emotions={EmotionKind.JOY: 0.8, EmotionKind.ANGER: 0.2},
        )


def test_model_expression_profile_contains_default_au_and_rules() -> None:
    config = VTubeStudioModelConfig()

    assert "嘴角上扬" in config.expression_profile.units
    smile = config.expression_profile.units["嘴角上扬"]
    assert smile.emotion_correlations[EmotionKind.JOY] > 0
    assert smile.emotion_correlations[EmotionKind.SADNESS] < 0
    assert smile.priority > 0
    assert smile.targets[0].action == SemanticAction.MOUTH_SMILE.value
    assert smile.targets[0].min is not None
    dumped_smile = smile.model_dump(mode="json", exclude_none=True)
    assert "id" not in dumped_smile
    assert "tags" not in dumped_smile
    assert any(rule.kind is ExpressionRuleKind.MUTEX for rule in config.expression_profile.rules)


def test_model_profile_can_override_au_range_per_model() -> None:
    config = VTubeStudioModelConfig()
    config.expression_profile.units["嘴角上扬"].targets[0].min = 0.80
    config.expression_profile.units["嘴角上扬"].targets[0].max = 0.90
    selector = ExpressionSelector(
        config.expression_profile.to_units(),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        combination_rules=config.expression_profile.to_rules(),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    values = {target.action: target.value for target in selected.targets}
    assert 0.80 <= values[SemanticAction.MOUTH_SMILE.value] <= 0.90


def test_model_profile_can_add_custom_au_and_rule() -> None:
    config = VTubeStudioModelConfig()
    config.expression_profile.units["自定义开心抬眉"] = ExpressionUnitConfig(
        regions=[ExpressionRegion.BROW],
        targets=[
            ExpressionTargetConfig(
                action=SemanticAction.BROW_HEIGHT.value,
                min=0.82,
                max=0.92,
                jitter=0.0,
            ),
        ],
        emotion_correlations={EmotionKind.JOY: 1.0, EmotionKind.ANGER: -1.0},
        priority=90,
        activation_threshold=0.0,
    )
    config.expression_profile.rules.append(
        ExpressionRuleConfig(
            id="自定义开心抬眉增强笑",
            kind=ExpressionRuleKind.SYNERGY,
            unit_ids=["自定义开心抬眉", "嘴角上扬"],
            emotions=[EmotionKind.JOY],
            bonus=0.5,
        ),
    )
    selector = ExpressionSelector(
        config.expression_profile.to_units(),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        combination_rules=config.expression_profile.to_rules(),
    )

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.JOY: 1.0},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    assert "自定义开心抬眉" in {unit.id for unit in selected.units}
    assert selected.score > 0.5


def test_unsupported_semantic_action_skips_au() -> None:
    unsupported = ExpressionUnit(
        id="仅嘴部纵向",
        regions=frozenset({ExpressionRegion.MOUTH}),
        targets=(ExpressionTarget(SemanticAction.MOUTH_Y.value, value_range=(0.4, 0.8)),),
        emotion_correlations={EmotionKind.JOY: 1.0},
        activation_threshold=0.0,
    )
    selector = ExpressionSelector(
        [unsupported, *BUILTIN_EXPRESSION_UNITS],
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

    assert "仅嘴部纵向" not in {unit.id for unit in selected.units}


def test_mutex_rule_keeps_only_one_mouth_corner_au() -> None:
    selector = _selector()

    selected = selector.select(
        EmotionRequest(
            emotions={EmotionKind.SADNESS: 1.0},
            intensity=1.0,
            randomness=0.0,
        ),
    )

    unit_ids = {unit.id for unit in selected.units}
    assert "嘴角下压" in unit_ids
    assert "嘴角上扬" not in unit_ids
    assert "嘴角平直" not in unit_ids


def test_synergy_rule_increases_compatible_combo_score() -> None:
    expression_profile = default_expression_profile()
    no_synergy_rules = tuple(
        rule for rule in expression_profile.to_rules() if rule.kind is not ExpressionRuleKind.SYNERGY
    )
    with_synergy = ExpressionSelector(
        expression_profile.to_units(),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        combination_rules=expression_profile.to_rules(),
    )
    without_synergy = ExpressionSelector(
        expression_profile.to_units(),
        default_vtube_studio_semantic_profile(),
        rng=random.Random(1),
        combination_rules=no_synergy_rules,
    )
    request = EmotionRequest(
        emotions={EmotionKind.JOY: 1.0},
        intensity=1.0,
        randomness=0.0,
    )

    assert with_synergy.select(request).score > without_synergy.select(request).score


def test_parameter_range_randomizes_within_binding_range() -> None:
    selector = _selector(rng_seed=2)

    stable = selector.preview(
        EmotionRequest(
            emotions={EmotionKind.SADNESS: 1.0},
            intensity=0.8,
            randomness=0.0,
            value_jitter=0.0,
        ),
    )
    jittered = selector.preview(
        EmotionRequest(
            emotions={EmotionKind.SADNESS: 1.0},
            intensity=0.8,
            randomness=1.0,
            value_jitter=0.1,
        ),
    )

    stable_values = {target.action: target.value for target in stable.targets}
    jittered_values = {target.action: target.value for target in jittered.targets}
    assert stable_values != jittered_values
    assert all(-1.0 <= value <= 1.0 for value in jittered_values.values())


def test_history_avoidance_penalizes_repeated_expression() -> None:
    selector = _selector()
    request = EmotionRequest(
        emotions={EmotionKind.JOY: 1.0},
        intensity=0.8,
        randomness=0.0,
        history_avoidance=1.0,
    )

    first = selector.select(request)
    second = selector.preview(request)

    assert second.score < first.score


async def test_expression_service_applies_semantic_tweens() -> None:
    sender = _SenderRecorder()
    tween = ParameterTweenEngine(sender)
    profile = default_vtube_studio_semantic_profile()
    expression_profile = default_expression_profile()
    selector = ExpressionSelector(
        expression_profile.to_units(),
        profile,
        rng=random.Random(1),
        combination_rules=expression_profile.to_rules(),
    )
    service = ExpressionService(
        platform=_SemanticVtsPlatform(
            tween=tween,
            adapter=VTubeStudioSemanticAdapter(profile),
        ),
        selector=selector,
        expression_profile=expression_profile,
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

    profile = default_vtube_studio_semantic_profile()
    expression_profile = default_expression_profile()
    selector = ExpressionSelector(
        expression_profile.to_units(),
        profile,
        rng=random.Random(1),
        combination_rules=expression_profile.to_rules(),
    )
    service = ExpressionService(
        platform=_SemanticVtsPlatform(
            tween=tween,
            adapter=VTubeStudioSemanticAdapter(profile),
        ),
        selector=selector,
        expression_profile=expression_profile,
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
    expression_profile = default_expression_profile()
    selector = ExpressionSelector(
        expression_profile.to_units(),
        profile,
        rng=random.Random(1),
        combination_rules=expression_profile.to_rules(),
    )
    service = ExpressionService(
        platform=_SemanticVtsPlatform(
            tween=_CapturingTween(sender),
            adapter=VTubeStudioSemanticAdapter(profile),
        ),
        selector=selector,
        expression_profile=expression_profile,
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


async def test_reload_model_config_persists_backfilled_semantic_profile_and_au_profile(
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
    assert "expression_profile" in raw
    assert "嘴角上扬" in raw["expression_profile"]["units"]
    assert raw["expression_profile"]["units"]["嘴角上扬"]["emotion_correlations"]["joy"] > 0


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

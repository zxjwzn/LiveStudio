"""Semantic controller output tests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import pytest
from pydantic import ValidationError

from livestudio.services.animations.controllers import (
    BlinkController,
    BlinkControllerSettings,
    BreathingController,
    BreathingControllerSettings,
    MouthExpressionController,
    MouthExpressionControllerSettings,
)
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.animations.templates import AnimationTemplatePlayer
from livestudio.services.platforms import PlatformService
from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticTweenRequest,
)
from livestudio.tween import ControlledParameterState, ParameterTweenEngine


class _TemplatePlayer(AnimationTemplatePlayer):
    def __init__(self, platform: PlatformService) -> None:
        self._platform = platform

    async def load(self) -> None:
        pass

    async def reload(self) -> None:
        pass


class _SemanticPlatform(PlatformService):
    def __init__(self) -> None:
        self.requests: list[SemanticTweenRequest] = []
        self._tween = ParameterTweenEngine(self._send)

    @property
    def name(self) -> str:
        return "semantic-test"

    @property
    def tween(self) -> ParameterTweenEngine:
        return self._tween

    async def tween_semantic(self, request: SemanticTweenRequest) -> None:
        self.requests.append(request)

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _send(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        _ = states, mode


def _runtime(platform: _SemanticPlatform) -> PlatformAnimationRuntime:
    return PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )


async def test_blink_controller_outputs_eye_open_semantic_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_duration: float) -> None:
        pass

    monkeypatch.setattr("asyncio.sleep", no_sleep)
    monkeypatch.setattr("random.uniform", lambda _start, _end: 0.01)
    platform = _SemanticPlatform()
    controller = BlinkController(
        _runtime(platform),
        "blink",
        BlinkControllerSettings(
            close_duration=0,
            open_duration=0,
            closed_hold=0,
        ),
    )

    await controller.run_cycle()

    assert [request.targets[0].action for request in platform.requests[:2]] == [
        SemanticAction.EYE_OPEN.value,
        SemanticAction.EYE_OPEN.value,
    ]
    assert [request.targets[0].value for request in platform.requests[:2]] == [0.0, 1.0]


async def test_breathing_controller_uses_normalized_pitch_amplitude() -> None:
    platform = _SemanticPlatform()
    controller = BreathingController(
        _runtime(platform),
        "breathing",
        BreathingControllerSettings(
            pitch_amplitude=0.2,
            inhale_duration=0,
            exhale_duration=0,
        ),
    )

    await controller.run_cycle()

    assert [request.targets[0].action for request in platform.requests] == [
        SemanticAction.HEAD_PITCH.value,
        SemanticAction.HEAD_PITCH.value,
    ]
    assert [request.targets[0].value for request in platform.requests] == [0.2, -0.2]


def test_controller_settings_reject_legacy_parameter_ranges() -> None:
    with pytest.raises(ValidationError):
        BreathingControllerSettings.model_validate(
            {
                "min_value": -3.0,
                "max_value": 3.0,
            },
        )


async def test_mouth_expression_controller_uses_mouth_smile_semantic_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("random.uniform", lambda _start, end: end)
    monkeypatch.setattr("random.choice", lambda values: values[0])
    platform = _SemanticPlatform()
    controller = MouthExpressionController(
        _runtime(platform),
        "mouth_expression",
        MouthExpressionControllerSettings(
            smile_amplitude=0.6,
            min_duration=0,
            max_duration=0,
        ),
    )

    await controller.run_cycle()

    assert platform.requests[0].targets[0].action == SemanticAction.MOUTH_SMILE.value
    assert platform.requests[0].targets[0].value == 0.6

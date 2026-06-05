"""测试通用动作控制器的输出"""

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
    EyeCenteringController,
    EyeCenteringControllerSettings,
    MouthExpressionController,
    MouthExpressionControllerSettings,
)
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.animations.templates import AnimationTemplatePlayer
from livestudio.services.platforms import PlatformService
from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionState,
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
        self.semantic_values: dict[str, SemanticActionState] = {}
        self._tween = ParameterTweenEngine(self.send_parameter_states)

    @property
    def name(self) -> str:
        return "semantic-test"

    @property
    def tween(self) -> ParameterTweenEngine:
        return self._tween

    async def tween_semantic(self, request: SemanticTweenRequest) -> None:
        self.requests.append(request)

    async def get_semantic_value(self, action: str) -> SemanticActionState | None:
        return self.semantic_values.get(action)

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"] = "set",
    ) -> None:
        _ = states, mode


def _runtime(platform: _SemanticPlatform) -> PlatformAnimationRuntime:
    return PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )


async def test_blink_controller_outputs_eye_open_semantic_actions() -> None:
    platform = _SemanticPlatform()
    platform.semantic_values[SemanticAction.EYE_OPEN.value] = SemanticActionState(
        action=SemanticAction.EYE_OPEN.value,
        value=0.75,
        platform_values={"EyeOpenLeft": 0.75, "EyeOpenRight": 0.75},
    )
    controller = BlinkController(
        _runtime(platform),
        "blink",
        BlinkControllerSettings(
            close_duration=0,
            open_duration=0,
            closed_hold=0,
            min_interval=0.001,
            max_interval=0.001,
        ),
    )

    await controller.run_cycle()

    assert [request.targets[0].action for request in platform.requests[:2]] == [
        SemanticAction.EYE_OPEN.value,
        SemanticAction.EYE_OPEN.value,
    ]
    assert [request.targets[0].value for request in platform.requests[:2]] == [0.0, 1.0]
    assert platform.requests[0].targets[0].start_value == 0.75


async def test_breathing_controller_uses_normalized_pitch_amplitude() -> None:
    platform = _SemanticPlatform()
    platform.semantic_values[SemanticAction.HEAD_PITCH.value] = SemanticActionState(
        action=SemanticAction.HEAD_PITCH.value,
        value=-0.1,
        platform_values={"FaceAngleY": -3.0},
    )
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
    assert platform.requests[0].targets[0].start_value == -0.1


def test_controller_settings_reject_legacy_parameter_ranges() -> None:
    with pytest.raises(ValidationError):
        BreathingControllerSettings.model_validate(
            {
                "min_value": -3.0,
                "max_value": 3.0,
            },
        )


async def test_mouth_expression_controller_uses_mouth_smile_semantic_action() -> None:
    platform = _SemanticPlatform()
    platform.semantic_values[SemanticAction.MOUTH_SMILE.value] = SemanticActionState(
        action=SemanticAction.MOUTH_SMILE.value,
        value=0.4,
        platform_values={"MouthSmile": 0.4},
    )
    controller = MouthExpressionController(
        _runtime(platform),
        "mouth_expression",
        MouthExpressionControllerSettings(
            smile_amplitude=0.0,
            min_duration=0,
            max_duration=0,
        ),
    )

    await controller.run_cycle()

    assert platform.requests[0].targets[0].action == SemanticAction.MOUTH_SMILE.value
    assert platform.requests[0].targets[0].value == 0.0
    assert platform.requests[0].targets[0].start_value == 0.4


async def test_eye_centering_controller_offsets_gaze_from_head_pose() -> None:
    platform = _SemanticPlatform()
    platform.semantic_values[SemanticAction.HEAD_YAW.value] = SemanticActionState(
        action=SemanticAction.HEAD_YAW.value,
        value=0.4,
        platform_values={"FaceAngleX": 12.0},
    )
    platform.semantic_values[SemanticAction.HEAD_PITCH.value] = SemanticActionState(
        action=SemanticAction.HEAD_PITCH.value,
        value=-0.2,
        platform_values={"FaceAngleY": -6.0},
    )
    platform.semantic_values[SemanticAction.HEAD_ROLL.value] = SemanticActionState(
        action=SemanticAction.HEAD_ROLL.value,
        value=0.1,
        platform_values={"FaceAngleZ": 9.0},
    )
    controller = EyeCenteringController(
        _runtime(platform),
        "eye_centering",
        EyeCenteringControllerSettings(
            yaw_compensation=1.0,
            pitch_compensation=1.0,
            roll_to_x_compensation=0.5,
            roll_to_y_compensation=0.25,
            smoothing=0.0,
            deadzone=0.0,
            duration=0.0,
            update_interval=0.001,
        ),
    )

    await controller.run_cycle()

    request = platform.requests[0]
    assert [target.action for target in request.targets] == [
        SemanticAction.EYE_GAZE_X.value,
        SemanticAction.EYE_GAZE_Y.value,
    ]
    assert [target.value for target in request.targets] == [pytest.approx(-0.45), pytest.approx(0.175)]

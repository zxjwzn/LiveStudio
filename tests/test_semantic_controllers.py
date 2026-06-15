"""测试通用动作控制器的输出"""

from __future__ import annotations

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
from livestudio.services.semantic_actions.models import SemanticAction
from tests.conftest import _SemanticPlatform, _TemplatePlayer


def _runtime(platform: _SemanticPlatform) -> PlatformAnimationRuntime:
    return PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )


async def test_blink_controller_outputs_eye_open_semantic_actions() -> None:
    platform = _SemanticPlatform()
    platform.semantic_values[SemanticAction.EYE_OPEN.value] = 0.75
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

    assert [request.action_parameter_name for request in platform.requests[:2]] == [
        SemanticAction.EYE_OPEN.value,
        SemanticAction.EYE_OPEN.value,
    ]
    assert [request.end_value for request in platform.requests[:2]] == [0.0, 1.0]
    assert platform.requests[0].start_value == 0.75


async def test_breathing_controller_uses_normalized_pitch_amplitude() -> None:
    platform = _SemanticPlatform()
    platform.semantic_values[SemanticAction.HEAD_PITCH.value] = -0.1
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

    assert [request.action_parameter_name for request in platform.requests] == [
        SemanticAction.HEAD_PITCH.value,
        SemanticAction.HEAD_PITCH.value,
    ]
    assert [request.end_value for request in platform.requests] == [0.2, -0.2]
    assert platform.requests[0].start_value == -0.1


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
    platform.semantic_values[SemanticAction.MOUTH_SMILE.value] = 0.4
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

    assert platform.requests[0].action_parameter_name == SemanticAction.MOUTH_SMILE.value
    assert platform.requests[0].end_value == 0.0
    assert platform.requests[0].start_value == 0.4


async def test_eye_centering_controller_offsets_gaze_from_head_pose() -> None:
    platform = _SemanticPlatform()
    platform.semantic_values[SemanticAction.HEAD_YAW.value] = 0.4
    platform.semantic_values[SemanticAction.HEAD_PITCH.value] = -0.2
    platform.semantic_values[SemanticAction.HEAD_ROLL.value] = 0.1
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
    assert [request.action_parameter_name for request in platform.requests[:2]] == [
        SemanticAction.EYE_GAZE_X.value,
        SemanticAction.EYE_GAZE_Y.value,
    ]
    assert [request.end_value for request in platform.requests[:2]] == [
        pytest.approx(-0.45),
        pytest.approx(0.175),
    ]

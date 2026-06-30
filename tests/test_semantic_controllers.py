"""测试通用动作控制器的输出"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from livestudio.services.animations.controllers import (
    BlinkController,
    BlinkControllerSettings,
    BreathingController,
    BreathingControllerSettings,
    GazeController,
    GazeControllerSettings,
    MouthExpressionController,
    MouthExpressionControllerSettings,
)
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.semantic_actions import SemanticAction
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
    assert platform.requests[0].start_value is None


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
    assert platform.requests[0].start_value is None


async def test_gaze_controller_outputs_center_micro_jitter(monkeypatch) -> None:
    values = iter([0.75, 0.0, 0.0, 0.0])
    monkeypatch.setattr("livestudio.services.animations.controllers.semantic.gaze.random.random", lambda: 0.0)
    monkeypatch.setattr(
        "livestudio.services.animations.controllers.semantic.gaze.random.uniform",
        lambda left, right: left + (right - left) * next(values),
    )
    monkeypatch.setattr("livestudio.services.animations.controllers.semantic.gaze.asyncio.sleep", lambda _delay: _noop())

    platform = _SemanticPlatform()
    controller = GazeController(
        _runtime(platform),
        "gaze",
        GazeControllerSettings(
            center_micro_chance=1.0,
            micro_gaze_x_amplitude=0.2,
            micro_gaze_y_amplitude=0.1,
            min_micro_duration=0.05,
            max_micro_duration=0.05,
            min_micro_fixation=0,
            max_micro_fixation=0,
            head_follow_chance=1,
        ),
    )

    await controller.run_cycle()

    assert [request.action_parameter_name for request in platform.requests] == [
        SemanticAction.EYE_GAZE_X.value,
        SemanticAction.EYE_GAZE_Y.value,
        SemanticAction.HEAD_YAW.value,
        SemanticAction.HEAD_PITCH.value,
        SemanticAction.HEAD_ROLL.value,
    ]
    assert platform.requests[0].end_value == pytest.approx(0.1)
    assert platform.requests[1].end_value == pytest.approx(-0.1)
    assert platform.requests[2].end_value == 0.0
    assert platform.requests[3].end_value == 0.0
    assert platform.requests[4].end_value == 0.0


async def test_gaze_controller_can_reverse_follow_on_three_head_axes() -> None:
    platform = _SemanticPlatform()
    controller = GazeController(
        _runtime(platform),
        "gaze",
        GazeControllerSettings(
            head_follow_ratio=0.5,
            head_pitch_ratio=0.25,
            head_roll_ratio=0.1,
            reverse_head_chance=1.0,
        ),
    )

    head_yaw, head_pitch, head_roll, mode = controller._head_targets(0.8, -0.4, 1.0, "gaze")  # noqa: SLF001

    assert mode == "反向"
    assert head_yaw == pytest.approx(-0.4)
    assert head_pitch == pytest.approx(0.1)
    assert head_roll == pytest.approx(-0.08)


def test_gaze_defaults_prefer_fast_center_micro_and_slow_roaming() -> None:
    settings = GazeControllerSettings()

    assert settings.center_micro_chance >= 0.8
    assert settings.max_micro_duration <= 0.05
    assert settings.min_micro_fixation >= 0.015
    assert settings.max_micro_fixation <= 0.03
    assert settings.drift_chance >= 0.7
    assert settings.dart_chance <= 0.1
    assert settings.max_drift_duration > settings.max_saccade_duration


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
    assert platform.requests[0].start_value is None


async def _noop() -> None:
    return None

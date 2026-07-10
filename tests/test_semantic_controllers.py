"""测试通用动作控制器的输出"""

from __future__ import annotations

import numpy as np
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
    MouthSyncController,
    MouthSyncControllerSettings,
)
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.audio_stream import (
    AudioChunk,
    AudioChunkAnalysis,
    AudioSourceKind,
    AudioStreamSource,
)
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


class _FakeAudioSource(AudioStreamSource):
    """最小音频源:仅暴露 _publish_chunk 供测试喂数据块"""

    async def _do_start(self) -> None:
        pass

    async def _do_stop(self) -> None:
        self._clear_subscriptions()

    def emit(self, chunk: AudioChunk) -> None:
        self._publish_chunk(chunk)


def _audio_chunk(rms: float) -> AudioChunk:
    return AudioChunk(
        frames=128,
        samplerate=48000,
        channels=1,
        data=np.zeros((128, 1), dtype=np.float32),
        source=AudioSourceKind.TTS,
        analysis=AudioChunkAnalysis(rms=rms),
    )


def _mouth_sync(platform: _SemanticPlatform, *, priority: int = 99) -> tuple[
    MouthSyncController, _FakeAudioSource
]:
    audio = _FakeAudioSource()
    controller = MouthSyncController(
        _runtime(platform),
        "mouth_sync",
        MouthSyncControllerSettings(priority=priority, update_interval=0.001),
        audio,
    )
    controller._audio_subscription = audio.subscribe(queue_maxsize=8)  # noqa: SLF001
    return controller, audio


async def test_mouth_sync_silent_yields_priority() -> None:
    """静音(rms <= noise_floor,目标开度 0)时以优先级 0 发布,让其他请求可接管 MOUTH_OPEN"""

    platform = _SemanticPlatform()
    controller, audio = _mouth_sync(platform, priority=99)

    audio.emit(_audio_chunk(rms=0.0))
    await controller.run_cycle()

    request = platform.requests[-1]
    assert request.action_parameter_name == SemanticAction.MOUTH_OPEN.value
    assert request.priority == 0
    assert request.end_value == 0.0


async def test_mouth_sync_speaking_holds_priority() -> None:
    """说话(目标开度 > 0)时保持配置高优先级独占唇形同步"""

    platform = _SemanticPlatform()
    audio = _FakeAudioSource()
    controller = MouthSyncController(
        _runtime(platform),
        "mouth_sync",
        MouthSyncControllerSettings(
            priority=99,
            noise_floor=0.01,
            voice_ceiling=0.2,
            update_interval=0.001,
        ),
        audio,
    )
    controller._audio_subscription = audio.subscribe(queue_maxsize=8)  # noqa: SLF001

    audio.emit(_audio_chunk(rms=0.1))  # 处于 noise_floor 与 voice_ceiling 之间 -> 语音
    await controller.run_cycle()

    request = platform.requests[-1]
    assert request.priority == 99
    assert request.end_value > 0.0


async def test_mouth_sync_no_audio_yields_priority() -> None:
    """无音频块(超时)时以优先级 0 发布,让出 MOUTH_OPEN"""

    platform = _SemanticPlatform()
    controller, _audio = _mouth_sync(platform, priority=99)

    await controller.run_cycle()  # 不喂块 -> wait_for 超时

    request = platform.requests[-1]
    assert request.priority == 0
    assert request.end_value == 0.0


async def _noop() -> None:
    return None

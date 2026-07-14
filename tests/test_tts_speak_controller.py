"""TTSpeak oneshot 控制器(并列 speak 配置 + kind)"""

# ruff: noqa: SLF001

from __future__ import annotations

from typing import cast

from livestudio.services.animations.controllers.config import TTSpeakControllerSettings
from livestudio.services.animations.controllers.semantic.tts_speak import TTSpeakController
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.audio_stream import AudioStreamSource
from livestudio.services.audio_stream.models import AudioSourceKind
from livestudio.services.audio_stream.sources.tts.engines.fish_audio import (
    FishAudioConnectionConfig,
    FishAudioSpeakConfig,
    TtsSpeakRequest,
)


class _FakeRuntime:
    def __init__(self) -> None:
        self.platform = object()


class _FakeTtsSource:
    def __init__(self) -> None:
        self.calls: list[TtsSpeakRequest] = []

    async def speak(self, request: TtsSpeakRequest) -> None:
        self.calls.append(request)

    async def stop_speaking(self) -> None:
        return None


class _FakeTtsCfg:
    def __init__(self) -> None:
        self.fish_audio = FishAudioConnectionConfig(api_key="k")


class _FakeRouterCfg:
    def __init__(self) -> None:
        self.tts = _FakeTtsCfg()


class _FakeRouter:
    def __init__(self) -> None:
        self.is_started = True
        self._kind = AudioSourceKind.MICROPHONE
        self.tts_source = _FakeTtsSource()
        self.switch_calls: list[AudioSourceKind] = []
        self.config = _FakeRouterCfg()

    @property
    def active_source_kind(self) -> AudioSourceKind:
        return self._kind

    async def switch_source(self, kind: AudioSourceKind) -> None:
        self.switch_calls.append(kind)
        self._kind = kind


def _make_controller(settings: TTSpeakControllerSettings, router: _FakeRouter) -> TTSpeakController:
    return TTSpeakController(
        cast(PlatformAnimationRuntime, _FakeRuntime()),
        "tts_speak",
        settings,
        cast(AudioStreamSource, router),
    )


async def test_tts_speak_execute_opts_and_switch() -> None:
    router = _FakeRouter()
    settings = TTSpeakControllerSettings(
        kind="fish_audio",
        fish_audio=FishAudioSpeakConfig(model="s1", reference_id="rid", latency="low", speed=1.2),
    )
    ctrl = _make_controller(settings, router)
    await ctrl.execute(text="你好")
    assert router.switch_calls == [AudioSourceKind.TTS]
    request = router.tts_source.calls[0]
    assert request.text == "你好"
    assert request.subtitle == "你好"
    assert request.kind == "fish_audio"
    assert request.fish_audio.model == "s1"
    assert request.fish_audio.reference_id == "rid"
    assert request.fish_audio.latency == "low"
    assert request.fish_audio.speed == 1.2


async def test_tts_speak_skips_empty_text() -> None:
    router = _FakeRouter()
    ctrl = _make_controller(TTSpeakControllerSettings(), router)
    await ctrl.execute(text="  ")
    assert router.tts_source.calls == []


async def test_tts_speak_kwargs_override_fields() -> None:
    router = _FakeRouter()
    ctrl = _make_controller(
        TTSpeakControllerSettings(fish_audio=FishAudioSpeakConfig(speed=1.0)),
        router,
    )
    await ctrl.execute(text="hi", latency="normal")
    request = router.tts_source.calls[0]
    assert request.fish_audio.latency == "normal"  # kwargs 覆盖激活 speak 字段
    assert request.fish_audio.speed == 1.0  # 配置保留


async def test_tts_speak_uses_separate_subtitle_text() -> None:
    router = _FakeRouter()
    ctrl = _make_controller(TTSpeakControllerSettings(), router)

    await ctrl.execute(text="spoken", subtitle="displayed")

    request = router.tts_source.calls[0]
    assert request.text == "spoken"
    assert request.subtitle == "displayed"

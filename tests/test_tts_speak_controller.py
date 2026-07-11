"""TTSpeak oneshot 控制器(扁平 kind/model/reference_id/extra)"""

# ruff: noqa: SLF001

from __future__ import annotations

from livestudio.services.animations.controllers.config import TTSpeakControllerSettings
from livestudio.services.animations.controllers.semantic.tts_speak import TTSpeakController
from livestudio.services.audio_stream.models import AudioSourceKind
from livestudio.services.audio_stream.sources.tts.engines.fish_audio import FishAudioConnectionConfig


class _FakeRuntime:
    def __init__(self) -> None:
        self.platform = object()


class _FakeTtsSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def speak(self, text: str, **opts: object) -> None:
        self.calls.append((text, dict(opts)))

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


async def test_tts_speak_execute_flat_opts_and_switch() -> None:
    router = _FakeRouter()
    settings = TTSpeakControllerSettings(
        kind="fish_audio",
        model="s1",
        reference_id="rid",
        extra={"latency": "low", "speed": 1.2},
    )
    ctrl = TTSpeakController(_FakeRuntime(), "tts_speak", settings, router)  # type: ignore[arg-type]
    await ctrl.execute(text="你好")
    assert router.switch_calls == [AudioSourceKind.TTS]
    text, opts = router.tts_source.calls[0]
    assert text == "你好"
    assert opts["kind"] == "fish_audio"
    assert opts["model"] == "s1"
    assert opts["reference_id"] == "rid"
    assert opts["extra"]["latency"] == "low"
    assert opts["extra"]["speed"] == 1.2


async def test_tts_speak_skips_empty_text() -> None:
    router = _FakeRouter()
    ctrl = TTSpeakController(
        _FakeRuntime(),
        "tts_speak",
        TTSpeakControllerSettings(),
        router,  # type: ignore[arg-type]
    )
    await ctrl.execute(text="  ")
    assert router.tts_source.calls == []


async def test_tts_speak_kwargs_merge_into_extra() -> None:
    router = _FakeRouter()
    ctrl = TTSpeakController(
        _FakeRuntime(),
        "tts_speak",
        TTSpeakControllerSettings(extra={"speed": 1.0}),
        router,  # type: ignore[arg-type]
    )
    await ctrl.execute(text="hi", latency="normal")
    _, opts = router.tts_source.calls[0]
    assert opts["extra"]["latency"] == "normal"
    assert opts["extra"]["speed"] == 1.0

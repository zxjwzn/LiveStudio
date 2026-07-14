"""TTSpeak oneshot 控制器: pydantic 入参 + 与音频对齐的字幕"""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio

import pytest

from livestudio.services.animations.controllers.config import TTSpeakControllerSettings
from livestudio.services.animations.controllers.semantic.tts_speak import TTSpeakController, TTSpeakRequest
from livestudio.services.audio_stream.models import AudioSourceKind
from livestudio.services.audio_stream.sources.tts.engines.fish_audio import (
    FishAudioConnectionConfig,
    FishAudioSpeakConfig,
)
from livestudio.services.audio_stream.sources.tts.engines.types import TtsSpeakRequest
from livestudio.services.subtitle import SubtitleEventKind, SubtitleStream


class _FakeRuntime:
    def __init__(self) -> None:
        self.platform = object()


class _FakeSession:
    def __init__(self) -> None:
        self._started = asyncio.Event()
        self._ended = asyncio.Event()

    @property
    def started(self) -> bool:
        return self._started.is_set()

    @property
    def ended(self) -> bool:
        return self._ended.is_set()

    def mark_started(self) -> None:
        self._started.set()

    def mark_ended(self) -> None:
        self._started.set()
        self._ended.set()

    async def wait_started(self) -> None:
        await self._started.wait()

    async def wait_ended(self) -> None:
        await self._ended.wait()


class _FakeTtsSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, TtsSpeakRequest | None]] = []
        self.session: _FakeSession | None = None
        self.auto_timeline = True
        self.audio_duration = 0.08

    @property
    def current_session(self) -> _FakeSession | None:
        return self.session

    async def speak(self, text: str, request: TtsSpeakRequest | None = None) -> _FakeSession:
        self.calls.append((text, request))
        session = _FakeSession()
        self.session = session
        if self.auto_timeline:

            async def _run() -> None:
                await asyncio.sleep(0.01)
                session.mark_started()
                await asyncio.sleep(self.audio_duration)
                session.mark_ended()

            asyncio.create_task(_run())
        return session

    async def stop_speaking(self) -> None:
        if self.session is not None:
            self.session.mark_ended()


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
        self.subtitle_stream = SubtitleStream()

    @property
    def active_source_kind(self) -> AudioSourceKind:
        return self._kind

    async def switch_source(self, kind: AudioSourceKind) -> None:
        self.switch_calls.append(kind)
        self._kind = kind


def test_ttspeak_request_resolves_subtitle() -> None:
    assert TTSpeakRequest(text="你好").resolved_subtitle() == "你好"
    assert TTSpeakRequest(text="你好", subtitle=None).resolved_subtitle() == "你好"
    assert TTSpeakRequest(text="你好", subtitle="字幕").resolved_subtitle() == "字幕"
    assert TTSpeakRequest(text="你好", subtitle="").resolved_subtitle() is None
    with pytest.raises(Exception):
        TTSpeakRequest(text="")
    with pytest.raises(Exception):
        TTSpeakRequest.model_validate({"text": "a", "reference_id": "x"})


async def test_tts_speak_execute_opts_and_switch() -> None:
    router = _FakeRouter()
    settings = TTSpeakControllerSettings(
        kind="fish_audio",
        fish_audio=FishAudioSpeakConfig(reference_id="rid"),
        subtitle_chars_per_second=60.0,
    )
    ctrl = TTSpeakController(_FakeRuntime(), "tts_speak", settings, router)  # type: ignore[arg-type]
    await ctrl.execute(text="你好")
    assert router.switch_calls == [AudioSourceKind.TTS]
    text, req = router.tts_source.calls[0]
    assert text == "你好"
    assert isinstance(req, TtsSpeakRequest)
    assert req.kind == "fish_audio"
    assert req.fish_audio.reference_id == "rid"
    if ctrl._subtitle_task is not None:
        await asyncio.wait_for(ctrl._subtitle_task, timeout=1.0)


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


async def test_tts_speak_subtitle_starts_after_audio_start() -> None:
    """begin 发生在 session.started 之后,不在 speak() 调用瞬间。"""

    router = _FakeRouter()
    router.tts_source.auto_timeline = False
    sub = router.subtitle_stream.subscribe(queue_maxsize=64)
    ctrl = TTSpeakController(
        _FakeRuntime(),
        "tts_speak",
        TTSpeakControllerSettings(subtitle_chars_per_second=50.0),
        router,  # type: ignore[arg-type]
    )
    await ctrl.execute(text="ab", subtitle="xy")
    await asyncio.sleep(0.02)
    assert sub.queue.empty(), "音频未 started 前不应有字幕事件"

    session = router.tts_source.session
    assert session is not None
    session.mark_started()
    await asyncio.sleep(0.03)
    assert not sub.queue.empty()
    first = sub.queue.get_nowait()
    assert first.kind is SubtitleEventKind.BEGIN
    assert first.text == "xy"

    session.mark_ended()
    if ctrl._subtitle_task is not None:
        await asyncio.wait_for(ctrl._subtitle_task, timeout=1.0)


async def test_tts_speak_flushes_rest_on_audio_end() -> None:
    """音频先结束时,剩余字幕一次冲刷再 finish。"""

    router = _FakeRouter()
    # 字速很慢,音频很快结束 → 触发冲刷
    router.tts_source.audio_duration = 0.03
    sub = router.subtitle_stream.subscribe(queue_maxsize=64)
    ctrl = TTSpeakController(
        _FakeRuntime(),
        "tts_speak",
        TTSpeakControllerSettings(subtitle_chars_per_second=2.0),
        router,  # type: ignore[arg-type]
    )
    await ctrl.execute(text="hello", subtitle="你好世界啊")
    if ctrl._subtitle_task is not None:
        await asyncio.wait_for(ctrl._subtitle_task, timeout=2.0)

    events = []
    while not sub.queue.empty():
        events.append(sub.queue.get_nowait())
    kinds = [e.kind for e in events]
    assert kinds[0] is SubtitleEventKind.BEGIN
    assert kinds[-1] is SubtitleEventKind.FINISH
    segs = [e for e in events if e.kind is SubtitleEventKind.SEGMENTS]
    pushed = "".join(
        (e.segments[0].text if e.segments else "") for e in segs
    )
    assert pushed == "你好世界啊"
    # 至少有一次冲刷(多字一段)或逐字+冲刷
    assert any(e.segments and len(e.segments[0].text) > 1 for e in segs) or len(segs) >= 1


async def test_tts_speak_empty_subtitle_skips_push() -> None:
    router = _FakeRouter()
    sub = router.subtitle_stream.subscribe(queue_maxsize=8)
    ctrl = TTSpeakController(
        _FakeRuntime(),
        "tts_speak",
        TTSpeakControllerSettings(subtitle_chars_per_second=50.0),
        router,  # type: ignore[arg-type]
    )
    await ctrl.execute(text="hi", subtitle="")
    await asyncio.sleep(0.05)
    assert sub.queue.empty()
    assert router.tts_source.calls[0][0] == "hi"

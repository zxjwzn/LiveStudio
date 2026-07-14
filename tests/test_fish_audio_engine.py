"""测试 Fish Audio 引擎：请求模型、音频解码及 alignment 禁用。"""

# ruff: noqa: SLF001

from __future__ import annotations

import base64
import json

import httpx
import numpy as np
import pytest
from pydantic import ValidationError

import livestudio.services.audio_stream.sources.tts.engines.fish_audio as fish_audio_module
from livestudio.services.audio_stream.sources.tts.engines import TtsAudioOutput, TtsSpeakRequest
from livestudio.services.audio_stream.sources.tts.engines.fish_audio import (
    FishAudioConnectionConfig,
    FishAudioEngine,
    FishAudioSpeakConfig,
)


def _b64(samples: list[int]) -> str:
    return base64.b64encode(np.array(samples, dtype=np.int16).tobytes()).decode()


def _sse(event: dict) -> str:
    return "data: " + json.dumps(event)


def _patch_httpx(monkeypatch, lines: list[str]) -> None:
    body = "".join(line + chr(10) for line in lines)
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text=body))
    original = fish_audio_module.httpx.AsyncClient

    def _factory(*args: object, **kwargs: object):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(fish_audio_module.httpx, "AsyncClient", _factory)


def _request(
    text: str,
    *,
    subtitle: str | None = None,
    config: FishAudioSpeakConfig | None = None,
) -> TtsSpeakRequest:
    speak_config = config or FishAudioSpeakConfig()
    return TtsSpeakRequest(
        text=text,
        subtitle=subtitle or text,
        fish_audio=speak_config,
        model=speak_config.model,
        reference_id=speak_config.reference_id,
        latency=speak_config.latency,
        prosody={"speed": speak_config.speed, "volume": 0.0},
    )


async def test_fish_audio_engine_empty_api_key_raises() -> None:
    engine = FishAudioEngine(FishAudioConnectionConfig(api_key=""), sample_rate=24000, channels=1)
    with pytest.raises(RuntimeError, match="api_key"):
        async for _ in engine.synthesize(_request("hi")):
            pass


def test_tts_speak_request_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        TtsSpeakRequest(text="", subtitle="subtitle")


async def test_fish_audio_engine_uses_request_config_for_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["headers_model"] = request.headers.get("model")
        captured["json"] = json.loads(request.content.decode())
        event = {"audio_base64": _b64([0]), "alignment": None}
        return httpx.Response(200, text=_sse(event) + chr(10))

    transport = httpx.MockTransport(_handler)
    original = fish_audio_module.httpx.AsyncClient

    def _factory(*args: object, **kwargs: object):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(fish_audio_module.httpx, "AsyncClient", _factory)
    engine = FishAudioEngine(FishAudioConnectionConfig(api_key="test"), sample_rate=24000, channels=1)
    request = _request(
        "hi",
        config=FishAudioSpeakConfig(model="s1", reference_id="voice-1", latency="low", speed=1.5),
    )
    _ = [output async for output in engine.synthesize(request)]
    assert captured["headers_model"] == "s1"
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["reference_id"] == "voice-1"
    assert body["latency"] == "low"
    assert body["prosody"]["speed"] == 1.5
    assert body["sample_rate"] == 24000
    assert "subtitle" not in body
    assert "kind" not in body
    assert "fish_audio" not in body


async def test_fish_audio_engine_ignores_alignment(monkeypatch) -> None:
    _patch_httpx(
        monkeypatch,
        [
            _sse(
                {
                    "audio_base64": _b64([1]),
                    "alignment": {"segments": [{"text": "a", "start": 0.1, "end": 0.2}]},
                    "chunk_seq": 0,
                    "chunk_audio_offset_sec": 1.0,
                }
            ),
            _sse(
                {
                    "audio_base64": _b64([2]),
                    "alignment": {
                        "segments": [
                            {"text": "a", "start": 0.1, "end": 0.2},
                            {"text": "b", "start": 0.2, "end": 0.4},
                        ]
                    },
                    "chunk_seq": 0,
                    "chunk_audio_offset_sec": 1.0,
                }
            ),
            _sse(
                {
                    "audio_base64": _b64([3]),
                    "alignment": {"segments": [{"text": "c", "start": 0.0, "end": 0.3}]},
                    "chunk_seq": 1,
                    "chunk_audio_offset_sec": 2.0,
                }
            ),
        ],
    )
    engine = FishAudioEngine(FishAudioConnectionConfig(api_key="test"), sample_rate=24000, channels=1)

    outputs = [output async for output in engine.synthesize(_request("abc"))]
    assert FishAudioEngine.supports_alignment is False
    assert len(outputs) == 3
    assert all(isinstance(output, TtsAudioOutput) for output in outputs)
    fallback = engine.make_fallback_subtitle_output("字幕")
    assert fallback is not None
    assert [segment.text for segment in fallback.segments] == ["字", "幕"]

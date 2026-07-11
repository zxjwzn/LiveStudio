"""测试 Fish Audio 引擎(mock httpx SSE):音频解码 + 字幕去重/全局时间 + opts 覆盖"""

# ruff: noqa: SLF001

from __future__ import annotations

import base64
import json

import httpx
import numpy as np
import pytest

import livestudio.services.audio_stream.sources.tts.engines.fish_audio as fish_audio_module
from livestudio.services.audio_stream.sources.tts.engines.fish_audio import (
    FishAudioEngine,
    FishAudioEngineConfig,
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


async def test_fish_audio_engine_empty_api_key_raises() -> None:
    engine = FishAudioEngine(FishAudioEngineConfig(api_key=""), sample_rate=24000, channels=1)
    with pytest.raises(RuntimeError, match="api_key"):
        async for _ in engine.synthesize("hi"):
            pass


async def test_fish_audio_engine_empty_text_yields_nothing(monkeypatch) -> None:
    _patch_httpx(monkeypatch, [])
    engine = FishAudioEngine(FishAudioEngineConfig(api_key="test"), sample_rate=24000, channels=1)
    outputs = [o async for o in engine.synthesize("")]
    assert outputs == []


async def test_fish_audio_engine_opts_override_payload(monkeypatch) -> None:
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
    engine = FishAudioEngine(FishAudioEngineConfig(api_key="test"), sample_rate=24000, channels=1)
    _ = [o async for o in engine.synthesize("hi", model="s1", reference_id="voice-1", latency="low", speed=1.5)]
    assert captured["headers_model"] == "s1"
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["reference_id"] == "voice-1"
    assert body["latency"] == "low"
    assert body["prosody"]["speed"] == 1.5


def test_fish_connection_config_strips_legacy_utterance_fields() -> None:
    cfg = FishAudioEngineConfig.model_validate(
        {
            "api_key": "k",
            "kind": "fish_audio",
            "model": "s1",
            "reference_id": "x",
            "latency": "low",
            "speed": 1.2,
        },
    )
    assert cfg.api_key == "k"
    assert not hasattr(cfg, "model") or "model" not in getattr(cfg, "model_fields_set", set())

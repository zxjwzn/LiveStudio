"""测试 Fish Audio 引擎(mock httpx SSE):音频解码 + 字幕去重/全局时间"""

# ruff: noqa: SLF001

from __future__ import annotations

import base64
import json

import httpx
import numpy as np
import pytest

import livestudio.services.audio_stream.sources.tts.engines.fish_audio as fish_audio_module
from livestudio.services.audio_stream.sources.tts.engines.base import TtsAudioOutput, TtsSubtitleOutput
from livestudio.services.audio_stream.sources.tts.engines.fish_audio import (
    FishAudioEngine,
    FishAudioEngineConfig,
)


def _b64(samples: list[int]) -> str:
    """int16 样本 -> base64 PCM"""

    return base64.b64encode(np.array(samples, dtype=np.int16).tobytes()).decode()


def _sse(event: dict) -> str:
    return "data: " + json.dumps(event)


def _patch_httpx(monkeypatch, lines: list[str]) -> None:
    """用 httpx.MockTransport 喂预定 SSE 行(替换 AsyncClient 注入 transport)"""

    body = "".join(line + "\n" for line in lines)
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, text=body))
    original = fish_audio_module.httpx.AsyncClient

    def _factory(*args: object, **kwargs: object):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(fish_audio_module.httpx, "AsyncClient", _factory)


async def test_fish_audio_engine_yields_audio_and_subtitle(monkeypatch) -> None:
    """SSE 事件 -> 音频块(int16->float32)+ 字幕段(全局时间=local+offset,去重)"""

    lines = [
        _sse(
            {
                "audio_base64": _b64([0, 16384, -16384]),
                "content": "hello world",
                "chunk_seq": 0,
                "chunk_audio_offset_sec": 0.0,
                "alignment": {
                    "audio_duration": 1.0,
                    "segments": [
                        {"text": "hello", "start": 0, "end": 0.5},
                        {"text": "world", "start": 0.5, "end": 1.0},
                    ],
                },
            },
        ),
        _sse(
            {
                "audio_base64": _b64([100, 200]),
                "content": "foo",
                "chunk_seq": 1,
                "chunk_audio_offset_sec": 1.0,
                "alignment": {
                    "audio_duration": 0.3,
                    "segments": [{"text": "foo", "start": 0, "end": 0.3}],
                },
            },
        ),
    ]
    _patch_httpx(monkeypatch, lines)

    engine = FishAudioEngine(
        FishAudioEngineConfig(api_key="test"),
        sample_rate=24000,
        channels=1,
    )
    outputs = [o async for o in engine.synthesize("hello world foo")]

    audios = [o for o in outputs if isinstance(o, TtsAudioOutput)]
    subs = [o for o in outputs if isinstance(o, TtsSubtitleOutput)]
    assert len(audios) == 2
    assert len(subs) == 2

    # 音频解码:int16 [0,16384,-16384] -> float32 [0, 0.5, -0.5]
    assert audios[0].frames == 3
    assert np.allclose(audios[0].data.reshape(-1), [0.0, 0.5, -0.5])

    # 字幕:第一块 2 段(全局=local,offset=0);第二块 1 段(全局=local+1.0)
    assert [s.text for s in subs[0].segments] == ["hello", "world"]
    assert subs[0].segments[0].start == 0.0
    assert subs[0].segments[1].end == 1.0
    assert subs[1].segments[0].text == "foo"
    assert subs[1].segments[0].start == 1.0  # offset 加上
    assert subs[1].segments[0].end == pytest.approx(1.3)


async def test_fish_audio_engine_dedupes_growing_snapshot(monkeypatch) -> None:
    """同一 chunk_seq 的 alignment 快照变完整时,只发新增段(不重复)"""

    lines = [
        _sse(
            {
                "audio_base64": _b64([0]),
                "content": "ab",
                "chunk_seq": 0,
                "chunk_audio_offset_sec": 0.0,
                "alignment": {
                    "audio_duration": 0.4,
                    "segments": [{"text": "a", "start": 0, "end": 0.2}],
                },
            },
        ),
        _sse(
            {
                "audio_base64": _b64([0]),
                "content": "ab",
                "chunk_seq": 0,
                "chunk_audio_offset_sec": 0.0,
                "alignment": {
                    "audio_duration": 0.4,
                    "segments": [
                        {"text": "a", "start": 0, "end": 0.2},
                        {"text": "b", "start": 0.2, "end": 0.4},
                    ],
                },
            },
        ),
    ]
    _patch_httpx(monkeypatch, lines)

    engine = FishAudioEngine(FishAudioEngineConfig(api_key="test"), sample_rate=24000, channels=1)
    subs = [o async for o in engine.synthesize("ab") if isinstance(o, TtsSubtitleOutput)]

    # 第一事件发 [a];第二事件(快照变完整)只发新增 [b],不重复 a
    assert len(subs) == 2
    assert [s.text for s in subs[0].segments] == ["a"]
    assert [s.text for s in subs[1].segments] == ["b"]


async def test_fish_audio_engine_empty_api_key_raises() -> None:
    """api_key 未配置时 raise"""

    engine = FishAudioEngine(FishAudioEngineConfig(api_key=""), sample_rate=24000, channels=1)
    with pytest.raises(RuntimeError, match="api_key"):
        async for _ in engine.synthesize("hi"):
            pass


async def test_fish_audio_engine_empty_text_yields_nothing(monkeypatch) -> None:
    """空文本不请求"""

    _patch_httpx(monkeypatch, [])
    engine = FishAudioEngine(FishAudioEngineConfig(api_key="test"), sample_rate=24000, channels=1)
    outputs = [o async for o in engine.synthesize("")]
    assert outputs == []


async def test_fish_audio_engine_null_alignment_no_subtitle(monkeypatch) -> None:
    """alignment 为 null 时不发字幕段(只发音频)"""

    lines = [
        _sse(
            {
                "audio_base64": _b64([0, 1]),
                "content": "x",
                "chunk_seq": 0,
                "chunk_audio_offset_sec": 0.0,
                "alignment": None,
            },
        ),
    ]
    _patch_httpx(monkeypatch, lines)
    engine = FishAudioEngine(FishAudioEngineConfig(api_key="test"), sample_rate=24000, channels=1)
    outputs = [o async for o in engine.synthesize("x")]
    assert len(outputs) == 1
    assert isinstance(outputs[0], TtsAudioOutput)

"""回归: FishAudioEngine.synthesize 取消/aclose 时 reader 任务收束,无 Exception ignored 噪声。

httpx 流式连接放在独立 reader 任务;外层 aclose/cancel 只 cancel reader,httpx anyio
cancel scope 在 reader 任务内 enter/exit,避免「cancel scope 跨任务」与
「async generator ignored GeneratorExit」。
"""

# ruff: noqa: SLF001

from __future__ import annotations

import asyncio
import base64
import contextlib
import gc
import io
import sys

import httpx
import numpy as np

import livestudio.services.audio_stream.sources.tts.engines.fish_audio as fish_audio_module
from livestudio.services.audio_stream.sources.tts.engines.fish_audio import (
    FishAudioConnectionConfig,
    FishAudioEngine,
    TtsSpeakRequest,
)


def _valid_sse_line() -> bytes:
    pcm = base64.b64encode(np.array([100, 200, 300], dtype=np.int16).tobytes()).decode()
    return f'data: {{"audio_base64":"{pcm}","alignment":null}}\n\n'.encode()


class _SlowStream(httpx.AsyncByteStream):
    """持续产出合法 SSE 行的慢流,永不自然结束。"""

    async def __aiter__(self):
        line = _valid_sse_line()
        while True:
            yield line
            await asyncio.sleep(0.05)

    async def aclose(self) -> None:
        return


def _patch_slow_stream(monkeypatch) -> None:
    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=_SlowStream(),
            headers={"content-type": "text/event-stream"},
        )

    transport = httpx.MockTransport(_handler)
    original = fish_audio_module.httpx.AsyncClient

    def _factory(*args: object, **kwargs: object):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(fish_audio_module.httpx, "AsyncClient", _factory)


async def _gc_noise(rounds: int = 3) -> str:
    err = io.StringIO()
    old = sys.stderr
    sys.stderr = err
    try:
        for _ in range(rounds):
            gc.collect()
            await asyncio.sleep(0.05)
        return err.getvalue()
    finally:
        sys.stderr = old


async def test_synthesize_aclose_cancels_reader_without_noise(monkeypatch) -> None:
    """aclose 后 reader 收束,stderr 无 Exception ignored / cancel scope 噪声。"""

    _patch_slow_stream(monkeypatch)
    engine = FishAudioEngine(FishAudioConnectionConfig(api_key="test"), sample_rate=24000, channels=1)

    gen = engine.synthesize(TtsSpeakRequest(text="hi", subtitle="hi"))
    first = await gen.__anext__()
    assert first is not None

    await gen.aclose()
    noise = await _gc_noise()
    assert "Exception ignored" not in noise, noise
    assert "cancel scope" not in noise, noise


async def test_synthesize_outer_cancel_via_aclosing_without_noise(monkeypatch) -> None:
    """外层 consumer 被 cancel(经 aclosing,命中循环体)时,无 Exception ignored。"""

    _patch_slow_stream(monkeypatch)
    engine = FishAudioEngine(FishAudioConnectionConfig(api_key="test"), sample_rate=24000, channels=1)
    blocked = asyncio.Event()

    async def consumer() -> None:
        async with contextlib.aclosing(engine.synthesize(TtsSpeakRequest(text="hi", subtitle="hi"))) as g:
            async for _ in g:
                await blocked.wait()

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.1)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    noise = await _gc_noise()
    assert "Exception ignored" not in noise, noise
    assert "cancel scope" not in noise, noise

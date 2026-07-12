"""Fish Audio TTS 引擎(SSE 流式 + 逐词对齐)

全局连接: ``FishAudioConnectionConfig``(api_key/endpoint)
发声参数: ``FishAudioSpeakConfig``(model/reference_id/latency/speed),由控制器展平为 opts 传入

取消契约: httpx 流式连接放在独立 reader 任务里,本生成器只从队列 yield。外层 aclose/
取消时只 cancel reader;httpx 的 anyio cancel scope 在 reader 任务内 enter/exit,避免
「cancel scope 跨任务」与「async generator ignored GeneratorExit」。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Literal

import httpx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from livestudio.utils.log import logger

from .base import TtsAudioOutput, TtsEngine, TtsOutput

FISH_AUDIO_TTS_URL = "https://api.fish.audio/v1/tts/stream/with-timestamp"
# reader -> outer 队列:有界反压;取消时用 put_nowait 哨兵,满则丢最旧再塞
_READER_QUEUE_MAXSIZE = 32


class FishAudioConnectionConfig(BaseModel):
    """Fish Audio 连接配置(全局 TTS 源槽位;密钥/端点)"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SPEAKERS"})

    api_key: str = Field(
        default="",
        description="Fish Audio API Bearer token(在 fish.audio 控制台获取)",
    )
    endpoint: str = Field(
        default=FISH_AUDIO_TTS_URL,
        description="TTS SSE 端点 URL(默认官方 with-timestamp 流)",
        json_schema_extra={"hidden": True},
    )


class FishAudioSpeakConfig(BaseModel):
    """Fish Audio 发声参数(per-model 音色:模型档位 / 说话人 / 延迟 / 语速)。

    与 ``FishAudioConnectionConfig`` 分工:连接(api_key/endpoint)全局,发声参数随模型。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SPEAKERS"})

    model: str = Field(
        default="s2.1-pro-free",
        description="Fish 模型/档位标识(如 s2.1-pro-free)",
    )
    reference_id: str | None = Field(
        default=None,
        description="音色/说话人 ID(fish.audio 控制台获取)",
    )
    latency: Literal["low", "balanced", "normal"] = Field(
        default="balanced",
        description="延迟档位(low=低延迟 / balanced=均衡 / normal=常规)",
    )
    speed: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="语速倍率(0.5~2.0)",
    )


class FishAudioEngine(TtsEngine):
    """Fish Audio 流式 TTS 引擎(PCM 音频 + 逐词 alignment 字幕)"""

    def __init__(
        self,
        config: FishAudioConnectionConfig,
        *,
        sample_rate: int,
        channels: int,
    ) -> None:
        super().__init__(sample_rate=sample_rate, channels=channels)
        self._config = config

    async def synthesize(self, text: str, **opts: object) -> AsyncGenerator[TtsOutput, None]:
        """合成文本:httpx 在独立 reader 任务,本生成器只从队列 yield。

        取消/aclose 时 finally 取消 reader;httpx ``async with`` 在 reader 任务内退出,
        避免跨任务 cancel scope 与 ignored GeneratorExit。
        """

        if not self._config.api_key:
            raise RuntimeError("Fish Audio api_key 未配置")
        if not text:
            return

        model = _as_str(opts.get("model"), "s2.1-pro-free")
        reference_id = _as_optional_str(opts.get("reference_id"))
        latency = _as_str(opts.get("latency"), "balanced")
        speed = _as_float(opts.get("speed"), 1.0)

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
            "model": model,
        }
        payload: dict[str, object] = {
            "text": text,
            "format": "pcm",
            "sample_rate": self._sample_rate,
            "latency": latency,
            "normalize": True,
            "temperature": 0.7,
            "top_p": 0.7,
            "chunk_length": 300,
            "prosody": {"speed": speed, "volume": 0},
        }
        if reference_id:
            payload["reference_id"] = reference_id

        endpoint = self._config.endpoint or FISH_AUDIO_TTS_URL
        timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
        queue: asyncio.Queue[TtsOutput | BaseException | None] = asyncio.Queue(
            maxsize=_READER_QUEUE_MAXSIZE,
        )

        async def _reader() -> None:
            """在独立任务里跑 httpx 流,产出放入 queue;结束/异常后塞 None 哨兵。"""

            try:
                async with (
                    httpx.AsyncClient(timeout=timeout) as client,
                    client.stream(
                        "POST",
                        endpoint,
                        headers=headers,
                        json=payload,
                    ) as response,
                ):
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        event = json.loads(line.removeprefix("data: "))
                        audio = self._decode_audio(event["audio_base64"])
                        if audio.frames > 0:
                            await queue.put(audio)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("Fish SSE reader 异常: {}", exc)
                _put_sentinel(queue, exc)
            finally:
                _put_sentinel(queue, None)

        task = asyncio.create_task(_reader())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            # aclose/取消/正常结束:取消 reader,等其在本任务的子任务里退出 httpx 上下文
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    def _decode_audio(self, audio_base64: str) -> TtsAudioOutput:
        pcm = base64.b64decode(audio_base64)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) * (1.0 / 32768.0)
        samples = np.repeat(samples.reshape(-1, 1), self._channels, axis=1) if self._channels > 1 else samples.reshape(-1, 1)
        return TtsAudioOutput(data=samples, frames=int(samples.shape[0]))


def _put_sentinel(
    queue: asyncio.Queue[TtsOutput | BaseException | None],
    item: BaseException | None,
) -> None:
    """非阻塞塞入异常或结束哨兵;队列满时丢最旧再塞,保证 reader finally 不阻塞。"""

    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(item)


def _as_str(value: object, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default

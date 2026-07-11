"""Fish Audio TTS 引擎(SSE 流式 + 逐词对齐)

全局连接: ``FishAudioConnectionConfig``(api_key/endpoint)
发声参数: speak(**opts) 中的 model/reference_id 及 extra 展平字段(latency/speed 等)

取消契约: httpx 流式连接放在独立 reader 任务里,本生成器只从队列 yield。外层 aclose/
取消时只 cancel reader;httpx 的 anyio cancel scope 在 reader 任务内 enter/exit,避免
「cancel scope 跨任务」与「async generator ignored GeneratorExit」。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from collections.abc import AsyncGenerator, Mapping
from typing import Any, Literal

import httpx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from livestudio.services.subtitle import SubtitleSegment

from .base import TtsAudioOutput, TtsEngine, TtsOutput, TtsSubtitleOutput

FISH_AUDIO_TTS_URL = "https://api.fish.audio/v1/tts/stream/with-timestamp"
_FishModel = Literal["s2.1-pro-free", "s2.1-pro", "s2-pro", "s1"]
_FishLatency = Literal["balanced", "normal", "low"]
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

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_fields(cls, data: Any) -> Any:
        """兼容旧 engine 嵌套:去掉 kind 与发声字段。"""

        if isinstance(data, dict):
            for key in ("kind", "model", "reference_id", "latency", "speed"):
                data.pop(key, None)
        return data


# 兼容旧导入名
FishAudioEngineConfig = FishAudioConnectionConfig


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

        flat = _flatten_opts(opts)
        model = _as_str(flat.get("model"), "s2.1-pro-free")
        reference_id = _as_optional_str(flat.get("reference_id"))
        latency = _as_str(flat.get("latency"), "balanced")
        speed = _as_float(flat.get("speed"), 1.0)

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
                async with httpx.AsyncClient(timeout=timeout) as client, client.stream(
                    "POST",
                    endpoint,
                    headers=headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    emitted = 0
                    snapshots: dict[int, list[SubtitleSegment]] = {}
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        event = json.loads(line.removeprefix("data: "))

                        audio = self._decode_audio(event["audio_base64"])
                        if audio.frames > 0:
                            await queue.put(audio)

                        alignment = event.get("alignment")
                        if alignment is not None:
                            offset = float(event.get("chunk_audio_offset_sec", 0.0))
                            chunk_seq = int(event.get("chunk_seq", 0))
                            snapshots[chunk_seq] = [
                                SubtitleSegment(
                                    text=str(seg["text"]),
                                    start=float(seg["start"]) + offset,
                                    end=float(seg["end"]) + offset,
                                )
                                for seg in alignment.get("segments", [])
                            ]
                            timeline = [
                                segment for cs in sorted(snapshots) for segment in snapshots[cs]
                            ]
                            new_segments = timeline[emitted:]
                            if new_segments:
                                emitted = len(timeline)
                                await queue.put(TtsSubtitleOutput(segments=list(new_segments)))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # 把异常交给外层 yield 循环 raise;队列满时丢最旧再塞,避免取消路径死锁
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
        samples = (
            np.repeat(samples.reshape(-1, 1), self._channels, axis=1)
            if self._channels > 1
            else samples.reshape(-1, 1)
        )
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


def _flatten_opts(opts: Mapping[str, object]) -> dict[str, object]:
    """合并 opts 与 opts['extra'](dict) 为扁平映射;顶层优先。"""

    flat: dict[str, object] = {}
    extra = opts.get("extra")
    if isinstance(extra, Mapping):
        for key, value in extra.items():
            if isinstance(key, str):
                flat[key] = value
    for key, value in opts.items():
        if key in ("extra", "kind"):
            continue
        flat[key] = value
    return flat


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

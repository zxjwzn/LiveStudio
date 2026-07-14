"""Fish Audio TTS 引擎。

引擎直接读取 ``TtsSpeakRequest`` 中已校验的文本与 ``FishAudioSpeakConfig``，
SSE 仅消费音频字段；Fish alignment 接口不可靠，字幕统一使用基类固定速率时间轴。
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
from .types import TtsProviderKind

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
        description="TTS SSE 音频端点 URL；仅使用 audio_base64，忽略 alignment",
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


class TtsSpeakRequest(BaseModel):
    """一次发声所需的文本、字幕文本和供应商配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    text: str = Field(min_length=1)
    subtitle: str = Field(min_length=1, exclude=True)
    kind: TtsProviderKind = Field(default="fish_audio", exclude=True)
    fish_audio: FishAudioSpeakConfig = Field(default_factory=FishAudioSpeakConfig, exclude=True)
    model: str = Field(default="s2.1-pro-free", exclude=True)
    reference_id: str | None = None
    format: Literal["pcm"] = "pcm"
    sample_rate: int = Field(default=24000, gt=0)
    latency: Literal["low", "balanced", "normal"] = "balanced"
    normalize: bool = True
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    top_p: float = Field(default=0.7, ge=0.0, le=1.0)
    chunk_length: int = Field(default=300, ge=100, le=300)
    prosody: dict[str, float] = Field(default_factory=lambda: {"speed": 1.0, "volume": 0.0})


class FishAudioEngine(TtsEngine):
    """Fish Audio 流式 TTS 引擎，只消费 PCM 音频。"""

    supports_alignment = False

    def __init__(
        self,
        config: FishAudioConnectionConfig,
        *,
        sample_rate: int,
        channels: int,
    ) -> None:
        super().__init__(sample_rate=sample_rate, channels=channels)
        self._config = config

    async def synthesize(self, request: TtsSpeakRequest) -> AsyncGenerator[TtsOutput, None]:
        """合成文本:httpx 在独立 reader 任务,本生成器只从队列 yield。

        取消/aclose 时 finally 取消 reader;httpx ``async with`` 在 reader 任务内退出,
        避免跨任务 cancel scope 与 ignored GeneratorExit。
        """

        if not self._config.api_key:
            raise RuntimeError("Fish Audio api_key 未配置")
        request = request.model_copy(update={"sample_rate": self._sample_rate})

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
            "model": request.model,
        }

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
                        content=request.model_dump_json(exclude_none=True),
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

"""Fish Audio TTS 引擎(SSE 流式)

全局连接: ``FishAudioConnectionConfig``(api_key/endpoint + model/latency/speed)
发声参数: ``FishAudioSpeakConfig``(仅 reference_id, 随模型/控制器)

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
    """Fish Audio 连接与全局发声参数(全局 TTS 源槽位)。

    密钥/端点 + 模型档位/延迟/语速;音色(reference_id)随模型控制器。
    """

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
    model: str = Field(
        default="s2.1-pro-free",
        description="Fish 模型/档位标识(如 s2.1-pro-free)",
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


class FishAudioSpeakConfig(BaseModel):
    """Fish Audio 发声参数(per-model:仅音色/说话人)。

    model/latency/speed 在全局 ``FishAudioConnectionConfig``。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SPEAKERS"})

    reference_id: str | None = Field(
        default=None,
        description="音色/说话人 ID(fish.audio 控制台获取)",
    )


class FishAudioSpeakRequest(BaseModel):
    """单次 Fish 合成请求(运行时,由控制器/调用方构造)。"""

    model_config = ConfigDict(extra="forbid")

    reference_id: str | None = None


class FishAudioEngine(TtsEngine):
    """Fish Audio 流式 TTS 引擎(PCM 音频)"""

    def __init__(
        self,
        config: FishAudioConnectionConfig,
        *,
        sample_rate: int,
        channels: int,
    ) -> None:
        super().__init__(sample_rate=sample_rate, channels=channels)
        self._config = config

    async def synthesize(
        self,
        text: str,
        request: BaseModel | None = None,
    ) -> AsyncGenerator[TtsOutput, None]:
        """合成文本:httpx 在独立 reader 任务,本生成器只从队列 yield。

        ``request`` 须为 ``FishAudioSpeakRequest``(或 None);model/latency/speed 来自全局连接。
        """

        if not self._config.api_key:
            raise RuntimeError("Fish Audio api_key 未配置")
        if not text:
            return

        if request is None:
            speak = FishAudioSpeakRequest()
        elif isinstance(request, FishAudioSpeakRequest):
            speak = request
        else:
            raise TypeError(
                f"FishAudioEngine.synthesize 需要 FishAudioSpeakRequest, 收到 {type(request).__name__}",
            )
        model = self._config.model
        latency = self._config.latency
        speed = self._config.speed
        reference_id = speak.reference_id

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

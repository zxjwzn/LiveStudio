"""Fish Audio TTS 引擎(SSE 流式 + 逐词对齐)

调 Fish Audio ``/v1/tts/stream/with-timestamp`` SSE 端点,流式产出 PCM 音频块 +
逐词 alignment 字幕段(全局时间)。alignment 是各 ``chunk_seq`` 的"最新累计快照"
(后续事件更完整),按 chunk_seq 存最新、全局时间线拼接,只 yield 新增段(去重)。
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator
from typing import Literal

import httpx
import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.subtitle import SubtitleSegment

from .base import TtsAudioOutput, TtsEngine, TtsOutput, TtsSubtitleOutput

FISH_AUDIO_TTS_URL = "https://api.fish.audio/v1/tts/stream/with-timestamp"


class FishAudioEngineConfig(BaseModel):
    """Fish Audio 引擎配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SPEAKERS"})

    kind: Literal["fish_audio"] = "fish_audio"
    api_key: str = Field(
        default="",
        description="Fish Audio API Bearer token(在 fish.audio 控制台获取)",
    )
    model: Literal["s2.1-pro-free", "s2.1-pro", "s2-pro", "s1"] = Field(
        default="s2.1-pro-free",
        description="TTS 模型(s2.1-pro-free 为免费档)",
    )
    reference_id: str | None = Field(
        default=None,
        description="Fish Audio 声音模型 ID(语音库/自建模型);留空用模型默认音色",
    )
    latency: Literal["balanced", "normal", "low"] = Field(
        default="balanced",
        description="延迟-质量权衡(low 最低延迟, normal 最佳质量)",
    )
    speed: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="语速倍率(0.5 慢一倍, 2.0 快一倍)",
    )


class FishAudioEngine(TtsEngine):
    """Fish Audio 流式 TTS 引擎(PCM 音频 + 逐词 alignment 字幕)"""

    def __init__(
        self,
        config: FishAudioEngineConfig,
        *,
        sample_rate: int,
        channels: int,
    ) -> None:
        super().__init__(sample_rate=sample_rate, channels=channels)
        self._config = config

    async def synthesize(self, text: str, **opts: object) -> AsyncIterator[TtsOutput]:
        _ = opts
        if not self._config.api_key:
            raise RuntimeError("Fish Audio api_key 未配置")
        if not text:
            return

        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "Content-Type": "application/json",
            "model": self._config.model,
        }
        payload: dict[str, object] = {
            "text": text,
            "format": "pcm",
            "sample_rate": self._sample_rate,
            "latency": self._config.latency,
            "normalize": True,
            "temperature": 0.7,
            "top_p": 0.7,
            "chunk_length": 300,
            "prosody": {"speed": self._config.speed, "volume": 0},
        }
        if self._config.reference_id:
            payload["reference_id"] = self._config.reference_id

        # 已发射的全局段数(去重:alignment 快照会变完整,只 yield 新增尾部)
        emitted = 0
        snapshots: dict[int, list[SubtitleSegment]] = {}
        timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client, client.stream(
            "POST",
            FISH_AUDIO_TTS_URL,
            headers=headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                event = json.loads(line.removeprefix("data: "))

                audio = self._decode_audio(event["audio_base64"])
                if audio.frames > 0:
                    yield audio

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
                    # 全局时间线 = 各 chunk_seq 最新快照按序拼接;只 yield 已发射之后的新增段
                    timeline = [
                        segment for cs in sorted(snapshots) for segment in snapshots[cs]
                    ]
                    new_segments = timeline[emitted:]
                    if new_segments:
                        emitted = len(timeline)
                        yield TtsSubtitleOutput(segments=list(new_segments))

    def _decode_audio(self, audio_base64: str) -> TtsAudioOutput:
        """base64 PCM(int16 LE) -> float32 (frames, channels)"""

        pcm = base64.b64decode(audio_base64)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) * (1.0 / 32768.0)
        # Fish Audio 输出单声道;按输出声道数复制
        samples = (
            np.repeat(samples.reshape(-1, 1), self._channels, axis=1)
            if self._channels > 1
            else samples.reshape(-1, 1)
        )
        return TtsAudioOutput(data=samples, frames=int(samples.shape[0]))

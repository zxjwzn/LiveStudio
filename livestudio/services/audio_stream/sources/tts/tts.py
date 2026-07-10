"""TTS 音频流源

第 0 阶段的占位发声(正弦音 ``_utterance`` + ``speak``/``stop_speaking`` + 路由器总线接管)
已移除,为接入真实 TTS API 做准备。当前仅保留空闲静音循环:源启动后持续发布响度 0 的
静音块(``source=TTS``),让 TTS 源像麦克风一样是连续音源,保持下游(唇形/电平/音频播放)
管线热开(第 1 阶段 speak 起步无开流延迟)。

路由器只转发当前激活源(无总线接管):要让 TTS 驱动唇形/音频播放,把激活源切到 TTS 即可。

第 1 阶段(接入 API):在本源实现 ``speak(text)`` -> 调 TTS API 拿 PCM 流 -> 按块
``_publish_chunk(source=TTS)``;发声期间需阻塞空闲静音循环(避免给节流加抖动)、取消-前置
语义等(参见路线图与历史实现)。
"""

from __future__ import annotations

import asyncio
import contextlib

import numpy as np

from ...base import AudioStreamSource
from ...models import AudioChunk, AudioSourceKind
from .config import TTSAudioStreamConfig


class TTSAudioStreamSource(AudioStreamSource):
    """TTS 音频流源(占位:仅空闲静音;第 1 阶段接入真实 engine)"""

    def __init__(self, config: TTSAudioStreamConfig) -> None:
        super().__init__()
        self.config = config
        self._idle_task: asyncio.Task[None] | None = None

    async def _do_start(self) -> None:
        """启动 TTS 音频流资源:开启空闲静音循环,保持总线持续有块(响度 0)"""

        self._idle_task = asyncio.ensure_future(self._idle_loop())

    async def _do_stop(self) -> None:
        """停止 TTS 音频流资源(取消空闲循环、释放订阅)"""

        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
        self._idle_task = None
        self._clear_subscriptions()

    async def _idle_loop(self) -> None:
        """空闲时持续发布响度 0 的静音块(source=TTS),保持下游管线热开。

        第 1 阶段接入 speak 后,需在发声期间阻塞本循环(避免给发声的 ``asyncio.sleep``
        节流加抖动)、发声结束恢复--届时用 ``asyncio.Event`` 实现。
        """

        samplerate = self.config.samplerate
        channels = self.config.channels
        block_frames = max(1, int(samplerate * 0.02))
        delay = block_frames / samplerate
        while True:
            self._publish_chunk(
                AudioChunk(
                    frames=block_frames,
                    samplerate=samplerate,
                    channels=channels,
                    data=np.zeros((block_frames, channels), dtype=np.float32),
                    source=AudioSourceKind.TTS,
                ),
            )
            await asyncio.sleep(delay)

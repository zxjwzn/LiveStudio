"""统一音频流路由器。"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import numpy as np

from livestudio.config import ConfigManager
from livestudio.log import logger

from .base import AudioStreamSource
from .config import AudioStreamConfigFile, AudioStreamRouterConfig
from .models import (
    AudioChunk,
    AudioChunkSubscription,
    AudioSourceKind,
)
from .sources import MicrophoneAudioStreamSource, TTSAudioStreamSource


class AudioStreamRouter(AudioStreamSource):
    """在多个音频源之间选择唯一活动源。"""

    def __init__(
        self,
    ) -> None:
        super().__init__()
        self.config_manager = ConfigManager(
            AudioStreamConfigFile,
            Path("config") / "audio_stream.yaml",
        )
        self._microphone_source: MicrophoneAudioStreamSource | None = None
        self._tts_source: TTSAudioStreamSource | None = None
        self._sources: dict[AudioSourceKind, AudioStreamSource] = {}
        self._active_source_kind: AudioSourceKind | None = None
        self._source_subscription: AudioChunkSubscription | None = None
        self._forward_task: asyncio.Task[None] | None = None
        self._initialized = False

    @property
    def config(self) -> AudioStreamRouterConfig:
        return self.config_manager.config.audio_stream

    @property
    def active_source_kind(self) -> AudioSourceKind:
        if self._active_source_kind is None:
            raise RuntimeError("音频流路由器尚未激活任何音频源")
        return self._active_source_kind

    @property
    def is_initialized(self) -> bool:
        """音频流路由器是否已初始化。"""

        return self._initialized

    @property
    def active_source(self) -> AudioStreamSource:
        if (
            self._active_source_kind is None
            or self._sources.get(self._active_source_kind) is None
        ):
            raise RuntimeError("音频流路由器当前没有可用的活动音频源")
        return self._sources[self._active_source_kind]

    @property
    def microphone_source(self) -> MicrophoneAudioStreamSource:
        """返回内置麦克风音频源。"""

        if self._microphone_source is None:
            raise RuntimeError("音频流路由器尚未初始化")
        return self._microphone_source

    @property
    def tts_source(self) -> TTSAudioStreamSource:
        """返回内置 TTS 音频源。"""

        if self._tts_source is None:
            raise RuntimeError("音频流路由器尚未初始化")
        return self._tts_source

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self.config_manager.load()

        self._microphone_source = MicrophoneAudioStreamSource(self.config.microphone)
        self._tts_source = TTSAudioStreamSource(self.config.tts)
        self._sources = {
            AudioSourceKind.MICROPHONE: self._microphone_source,
            AudioSourceKind.TTS: self._tts_source,
        }

        for source in self._sources.values():
            await source.initialize()
        self._active_source_kind = self.config.source
        self._source_subscription = self.active_source.subscribe(
            queue_maxsize=self.config.microphone.queue_maxsize,
        )
        self._initialized = True
        logger.info("音频流路由器已初始化，当前音频源: {}", self.active_source_kind)

    async def start(self) -> None:
        if self.is_started:
            return
        if not self._initialized:
            await self.initialize()

        await self.active_source.start()
        self._forward_task = asyncio.create_task(self._forward_chunks())
        self.is_started = True

    async def stop(self) -> None:
        """停止并释放音频流路由器资源。"""

        if not self._initialized:
            return

        await self._stop_forward_task()
        if self._source_subscription is not None:
            self.active_source.unsubscribe(self._source_subscription)
            self._source_subscription = None

        for source in self._sources.values():
            await source.stop()
        self._clear_subscriptions()
        await self.config_manager.save()
        self._microphone_source = None
        self._tts_source = None
        self._sources = {}
        self._active_source_kind = None
        self._initialized = False
        self.is_started = False

    async def restart(self) -> None:
        """重启音频流路由器并重新加载配置。"""

        await self.stop()
        await self.initialize()
        await self.start()

    async def switch_source(
        self,
        source_kind: AudioSourceKind,
    ) -> None:
        if self._active_source_kind == source_kind:
            return
        if not self._initialized:
            await self.initialize()

        was_started = self.is_started
        if was_started:
            await self._stop_forward_task()
            await self.active_source.stop()
        if self._source_subscription is not None:
            self.active_source.unsubscribe(self._source_subscription)
            self._source_subscription = None
        self._active_source_kind = source_kind
        self.config.source = source_kind
        self._source_subscription = self.active_source.subscribe(
            queue_maxsize=self.config.microphone.queue_maxsize,
        )
        await self.config_manager.save()

        if was_started:
            await self.active_source.start()
            self._forward_task = asyncio.create_task(self._forward_chunks())

        logger.info("音频流路由器已切换音频源: {}", source_kind)

    async def _stop_forward_task(self) -> None:
        task = self._forward_task
        self._forward_task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _forward_chunks(self) -> None:
        """将当前活动源的音频块广播给路由器订阅者。"""

        source_subscription = self._source_subscription
        if source_subscription is None:
            raise RuntimeError("音频流路由器尚未订阅活动音频源")
        try:
            while True:
                chunk = await source_subscription.queue.get()
                self._chunk_analysis(chunk)
                self._publish_chunk(chunk)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("音频流路由器转发任务异常")

    @staticmethod
    def _chunk_analysis(chunk: AudioChunk) -> None:
        """补充音频块通用分析结果，避免下游消费者重复计算。"""

        samples = np.asarray(chunk.data, dtype=np.float32)
        if samples.size == 0:
            rms = 0.0
            peak = 0.0
        else:
            flattened = samples.reshape(-1)
            rms = float(np.sqrt(np.mean(np.square(flattened))))
            peak = float(np.max(np.abs(flattened)))
        chunk.analysis.rms = rms
        chunk.analysis.peak = peak

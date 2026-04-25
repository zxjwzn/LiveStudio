"""统一音频流路由器。"""

from __future__ import annotations

from pathlib import Path

from livestudio.config import ConfigManager
from livestudio.log import logger

from .base import AudioStreamSource
from .config import AudioStreamConfigFile, AudioStreamRouterConfig
from .models import AudioChunk, AudioSourceKind
from .sources import MicrophoneAudioStreamSource, TTSAudioStreamSource


class AudioStreamRouter(AudioStreamSource):
    """在多个音频源之间选择唯一活动源。"""

    def __init__(
        self,
    ) -> None:
        self.config_manager = ConfigManager(
            AudioStreamConfigFile,
            Path("config") / "audio_stream.yaml",
        )
        self._microphone_source = MicrophoneAudioStreamSource()
        self._tts_source = TTSAudioStreamSource()
        self._sources: dict[AudioSourceKind, AudioStreamSource] = {
            AudioSourceKind.MICROPHONE: self._microphone_source,
            AudioSourceKind.TTS: self._tts_source,
        }
        self._active_source_kind: AudioSourceKind | None = None

    @property
    def config(self) -> AudioStreamRouterConfig:
        return self.config_manager.config.audio_stream

    @property
    def source_kind(self) -> AudioSourceKind:
        if self._active_source_kind is None:
            raise RuntimeError("音频流路由器尚未激活任何音频源")
        return self._active_source_kind

    @property
    def active_source(self) -> AudioStreamSource:
        if self._active_source_kind is None:
            raise RuntimeError("音频流路由器当前没有可用的活动音频源")
        return self._sources[self._active_source_kind]

    @property
    def microphone_source(self) -> MicrophoneAudioStreamSource:
        """返回内置麦克风音频源。"""

        return self._microphone_source

    @property
    def tts_source(self) -> TTSAudioStreamSource:
        """返回内置 TTS 音频源。"""

        return self._tts_source

    @property
    def is_started(self) -> bool:
        active_source_kind = self._active_source_kind
        if active_source_kind is None:
            return False
        return self._sources[active_source_kind].is_started

    async def initialize(self) -> None:
        await self.config_manager.load()

        self._microphone_source.apply_config(self.config.microphone)
        self._tts_source.apply_config(self.config.tts)

        for source in self._sources.values():
            await source.initialize()
        await self.switch_source(self.config.source)
        logger.info("音频流路由器已初始化，当前音频源: {}", self.source_kind)

    async def start(self) -> None:
        await self.active_source.start()

    async def stop(self) -> None:
        await self.active_source.stop()

    async def close(self) -> None:
        await self.active_source.close()
        await self.config_manager.save()

    async def read_chunk(self, timeout: float | None = None) -> AudioChunk:
        return await self.active_source.read_chunk(timeout=timeout)

    async def switch_source(
        self,
        source_kind: AudioSourceKind,
    ) -> None:
        next_source = self._sources.get(source_kind)
        if next_source is None:
            raise RuntimeError(f"未绑定音频源: {source_kind}")

        current_source_kind = self._active_source_kind
        if current_source_kind is source_kind:
            return

        current_source = (
            self._sources[current_source_kind]
            if current_source_kind is not None
            else None
        )
        if current_source is not None:
            await current_source.stop()

        self._active_source_kind = source_kind
        self.config.source = source_kind
        await next_source.start()

        logger.info("音频流路由器已切换音频源: {}", source_kind)

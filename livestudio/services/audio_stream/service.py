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
        self._initialized = False

    @property
    def config(self) -> AudioStreamRouterConfig:
        return self.config_manager.config.audio_stream

    @property
    def source_kind(self) -> AudioSourceKind:
        active_source_kind = self._active_source_kind
        if active_source_kind is None:
            raise RuntimeError("音频流路由器尚未激活任何音频源")
        return active_source_kind

    @property
    def active_source(self) -> AudioStreamSource | None:
        return self._get_active_source()

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
        active_source = self._get_active_source()
        return active_source.is_started if active_source is not None else False

    def bind_source(self, source: AudioStreamSource) -> None:
        source_kind = source.source_kind
        if source_kind in self._sources:
            raise ValueError(f"音频源已绑定: {source_kind}")
        self._sources[source_kind] = source

    async def initialize(self) -> None:
        await self.config_manager.load()
        self._apply_source_configs()
        for source in self._sources.values():
            await source.initialize()
        await self.switch_source(self.config.source, persist=False)
        self._initialized = True
        logger.info("音频流路由器已初始化，当前音频源: {}", self.source_kind)

    async def start(self) -> None:
        active_source = self._require_active_source()
        await active_source.start()

    async def stop(self) -> None:
        active_source = self._get_active_source()
        if active_source is None:
            return
        await active_source.stop()

    async def close(self) -> None:
        active_source = self._get_active_source()
        if active_source is not None:
            await active_source.close()

        for source_kind, source in self._sources.items():
            if active_source is not None and source_kind is self.source_kind:
                continue
            await source.close()

        await self.config_manager.save()

    async def read_chunk(self, timeout: float | None = None) -> AudioChunk:
        active_source = self._require_active_source()
        return await active_source.read_chunk(timeout=timeout)

    async def switch_source(
        self,
        source_kind: AudioSourceKind,
        *,
        persist: bool = True,
    ) -> None:
        next_source = self._sources.get(source_kind)
        if next_source is None:
            raise RuntimeError(f"未绑定音频源: {source_kind}")

        current_source = self._get_active_source()
        current_source_kind = self._active_source_kind
        if current_source_kind is source_kind:
            return

        if current_source is not None and current_source.is_started:
            await current_source.stop()

        self._active_source_kind = source_kind
        if persist:
            self.config.source = source_kind

        if self._initialized:
            await next_source.start()

        logger.info("音频流路由器已切换音频源: {}", source_kind)

    def _get_active_source(self) -> AudioStreamSource | None:
        active_source_kind = self._active_source_kind
        if active_source_kind is None:
            return None
        return self._sources.get(active_source_kind)

    def _require_active_source(self) -> AudioStreamSource:
        active_source = self._get_active_source()
        if active_source is None:
            raise RuntimeError("音频流路由器当前没有可用的活动音频源")
        return active_source

    def _apply_source_configs(self) -> None:
        self._microphone_source.apply_config(self.config.microphone)
        self._tts_source.apply_config(self.config.tts)

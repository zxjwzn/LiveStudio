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
        super().__init__()
        self.config_manager = ConfigManager(
            AudioStreamConfigFile,
            Path("config") / "audio_stream.yaml",
        )
        self._microphone_source: MicrophoneAudioStreamSource | None = None
        self._tts_source: TTSAudioStreamSource | None = None
        self._sources: dict[AudioSourceKind, AudioStreamSource] = {}
        self._active_source_kind: AudioSourceKind | None = None
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
        self._initialized = True
        logger.info("音频流路由器已初始化，当前音频源: {}", self.active_source_kind)

    async def start(self) -> None:
        if self.is_started:
            return
        if not self._initialized:
            await self.initialize()

        await self.active_source.start()
        self.is_started = True

    async def stop(self) -> None:
        """停止并释放音频流路由器资源。"""

        await self._stop(save_config=True)

    async def _stop(self, *, save_config: bool) -> None:
        """停止内部音频源并按需保存配置。"""

        if not self._initialized:
            return

        for source in self._sources.values():
            await source.stop()
        if save_config:
            await self.config_manager.save()
        self._microphone_source = None
        self._tts_source = None
        self._sources = {}
        self._active_source_kind = None
        self._initialized = False
        self.is_started = False

    async def restart(self) -> None:
        """重启音频流路由器并重新加载配置。"""

        await self._stop(save_config=False)
        await self.initialize()
        await self.start()

    async def read_chunk(self, timeout: float | None = None) -> AudioChunk:
        return await self.active_source.read_chunk(timeout=timeout)

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
            await self.active_source.stop()
        self._active_source_kind = source_kind
        self.config.source = source_kind
        await self.config_manager.save()

        if was_started:
            await self.active_source.start()

        logger.info("音频流路由器已切换音频源: {}", source_kind)

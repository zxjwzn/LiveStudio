"""TTS 音频流源占位实现。"""

from __future__ import annotations

from ...base import AudioStreamSource
from ...models import AudioChunk, AudioSourceKind
from .config import TTSAudioStreamConfig


class TTSAudioStreamSource(AudioStreamSource):
    """TTS HTTP 流音频源占位实现。"""

    def __init__(self) -> None:
        self._config = TTSAudioStreamConfig()
        self._started = False

    @property
    def config(self) -> TTSAudioStreamConfig:
        """返回当前 TTS 配置。"""

        return self._config

    def apply_config(self, config: TTSAudioStreamConfig) -> None:
        """应用外部注入的 TTS 配置。"""

        self._config = config

    @property
    def source_kind(self) -> AudioSourceKind:
        """返回当前音频源类型。"""

        return AudioSourceKind.TTS

    @property
    def is_started(self) -> bool:
        """返回当前 TTS 音频流是否已启动。"""

        return self._started

    async def initialize(self) -> None:
        """初始化 TTS 音频流占位资源。"""

    async def start(self) -> None:
        """启动 TTS 音频流占位资源。"""

        self._started = True

    async def stop(self) -> None:
        """停止 TTS 音频流占位资源。"""

        self._started = False

    async def close(self) -> None:
        """关闭 TTS 音频流占位资源。"""

        await self.stop()

    async def read_chunk(self, timeout: float | None = None) -> AudioChunk:
        """读取 TTS 音频块。当前为占位实现。"""

        _ = timeout
        raise NotImplementedError("TTSAudioStreamSource 尚未实现具体的流式音频读取逻辑")

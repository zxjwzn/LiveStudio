"""TTS 音频流源占位实现。"""

from __future__ import annotations

from ...base import AudioStreamSource
from ...models import AudioChunk, AudioSourceKind
from .config import TTSAudioStreamConfig


class TTSAudioStreamSource(AudioStreamSource):
    """TTS HTTP 流音频源占位实现。"""

    def __init__(self, config: TTSAudioStreamConfig) -> None:
        super().__init__()
        self.config = config

    async def initialize(self) -> None:
        """初始化 TTS 音频流占位资源。"""

    async def start(self) -> None:
        """启动 TTS 音频流占位资源。"""

        self.is_started = True

    async def stop(self) -> None:
        """停止 TTS 音频流占位资源。"""

        self.is_started = False

    async def read_chunk(self, timeout: float | None = None) -> AudioChunk:
        """读取 TTS 音频块。当前为占位实现。"""

        _ = timeout
        raise NotImplementedError("TTSAudioStreamSource 尚未实现具体的流式音频读取逻辑")

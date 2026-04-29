"""TTS 音频流源占位实现。"""

from __future__ import annotations

from ...base import AudioStreamSource
from .config import TTSAudioStreamConfig


class TTSAudioStreamSource(AudioStreamSource):
    """TTS HTTP 流音频源占位实现。"""

    def __init__(self, config: TTSAudioStreamConfig) -> None:
        super().__init__()
        self.config = config

    async def initialize(self) -> None:
        """初始化 TTS 音频流占位资源。"""

    async def restart(self) -> None:
        """重启 TTS 音频流占位资源。"""

        await self.stop()
        await self.initialize()
        await self.start()

    async def start(self) -> None:
        """启动 TTS 音频流占位资源。"""

        self.is_started = True

    async def stop(self) -> None:
        """停止 TTS 音频流占位资源。"""

        self.is_started = False

"""通用音频流抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import AudioChunk, AudioSourceKind


class AudioStreamSource(ABC):
    """统一音频流来源抽象。"""

    def __init__(self):
        self.is_started = False

    @abstractmethod
    async def initialize(self) -> None:
        """初始化音频源。"""

    @abstractmethod
    async def start(self) -> None:
        """启动音频源。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止音频源。"""

    async def restart(self) -> None:
        """重启音频源。"""

        await self.stop()
        await self.initialize()
        await self.start()

    @abstractmethod
    async def read_chunk(self, timeout: float | None = None) -> AudioChunk:
        """读取下一段音频块。"""

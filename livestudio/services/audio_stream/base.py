"""通用音频流抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import AudioChunk, AudioSourceKind


class AudioStreamSource(ABC):
    """统一音频流来源抽象。"""

    @property
    @abstractmethod
    def source_kind(self) -> AudioSourceKind:
        """返回音频源类型。"""

    @property
    @abstractmethod
    def is_started(self) -> bool:
        """返回音频源是否已启动。"""

    @abstractmethod
    async def initialize(self) -> None:
        """初始化音频源。"""

    @abstractmethod
    async def start(self) -> None:
        """启动音频源。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止音频源。"""

    @abstractmethod
    async def close(self) -> None:
        """关闭音频源。"""

    @abstractmethod
    async def read_chunk(self, timeout: float | None = None) -> AudioChunk:
        """读取下一段音频块。"""

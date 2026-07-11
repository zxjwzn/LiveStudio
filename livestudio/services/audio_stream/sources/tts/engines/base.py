"""TTS 引擎基类:规范各 TTS 供应商接入

``make_engine`` 按连接配置类型 / kind 分发。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from .fish_audio import FishAudioConnectionConfig


@dataclass(slots=True)
class TtsAudioOutput:
    """引擎产出的一段 PCM 音频(float32, 形状 (frames, channels))"""

    data: NDArray[np.float32]
    frames: int


TtsOutput = TtsAudioOutput


class TtsEngine(ABC):
    """TTS 引擎抽象基类"""

    def __init__(self, *, sample_rate: int, channels: int) -> None:
        self._sample_rate = sample_rate
        self._channels = channels

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    @abstractmethod
    def synthesize(self, text: str, **opts: object) -> AsyncGenerator[TtsOutput, None]:
        """合成文本;opts 含通用字段与 extra 展平字段。

        实现为异步生成器;调用方须 aclose(TTSAudioStreamSource 用 aclosing)。
        若引擎内部用 httpx 流,应把连接放在独立任务(见 FishAudioEngine),勿在生成器
        体内 async with 后直接 yield 挂起。
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(sample_rate={self._sample_rate}, channels={self._channels})"


def make_engine(config: FishAudioConnectionConfig, *, sample_rate: int, channels: int) -> TtsEngine:
    """由连接配置构造引擎(Fish 连接槽 -> FishAudioEngine)。"""

    from .fish_audio import FishAudioConnectionConfig as FishConn
    from .fish_audio import FishAudioEngine

    if isinstance(config, FishConn):
        return FishAudioEngine(config, sample_rate=sample_rate, channels=channels)
    raise TypeError(f"无法为连接配置类型 {type(config).__name__} 构造引擎")

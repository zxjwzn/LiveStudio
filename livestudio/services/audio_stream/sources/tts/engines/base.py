"""TTS 引擎基类:规范各 TTS 供应商接入

引擎输入文本,流式产出音频块(``TtsAudioOutput``)与字幕段(``TtsSubtitleOutput``)。
TTS 源迭代 ``synthesize`` 分发:音频块发到音频总线(``_publish_chunk``),字幕段发到
字幕流(``SubtitleStream``)。引擎可取消:迭代任务被 cancel 时生成器收到 GeneratorExit,
引擎应在 ``async with``/``finally`` 里清理(如关闭 HTTP 流)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from livestudio.services.subtitle import SubtitleSegment

if TYPE_CHECKING:
    from .fish_audio import FishAudioEngineConfig


@dataclass(slots=True)
class TtsAudioOutput:
    """引擎产出的一段 PCM 音频(float32, 形状 (frames, channels))"""

    data: NDArray[np.float32]
    frames: int


@dataclass(slots=True)
class TtsSubtitleOutput:
    """引擎产出的增量字幕段(仅本次新增段,已去重、全局时间)"""

    segments: list[SubtitleSegment]


TtsOutput = TtsAudioOutput | TtsSubtitleOutput


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
    def synthesize(self, text: str, **opts: object) -> AsyncIterator[TtsOutput]:
        """合成文本,按产出顺序 yield ``TtsAudioOutput | TtsSubtitleOutput``"""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(sample_rate={self._sample_rate}, channels={self._channels})"


def make_engine(config: FishAudioEngineConfig, *, sample_rate: int, channels: int) -> TtsEngine:
    """按引擎配置分发构造。

    暂用直字段(engine: FishAudioEngineConfig);加第二个引擎时改为判别联合,本函数按
    ``config.kind``/isinstance 分发即可。
    """
    from .fish_audio import FishAudioEngine

    return FishAudioEngine(config, sample_rate=sample_rate, channels=channels)

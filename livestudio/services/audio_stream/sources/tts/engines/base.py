"""TTS 引擎基类:规范各 TTS 供应商接入

引擎按 kind 分发(注册表 ``TTS_ENGINES`` + ``make_engine`` 在 ``engines`` 包)。
各供应商实现 ``synthesize``:输入文本,流式产出 PCM;锚点/队列/时钟由呈现层负责,引擎不碰。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import numpy as np
from numpy.typing import NDArray

from livestudio.services.subtitle import SubtitleSegment

if TYPE_CHECKING:
    from .fish_audio import TtsSpeakRequest


@dataclass(slots=True)
class TtsAudioOutput:
    """引擎产出的一段 PCM 音频(float32, 形状 (frames, channels))"""

    data: NDArray[np.float32]
    frames: int


@dataclass(slots=True)
class TtsSubtitleOutput:
    """引擎产出的增量字幕段。"""

    segments: list[SubtitleSegment]


TtsOutput = TtsAudioOutput | TtsSubtitleOutput


class TtsEngine(ABC):
    """TTS 引擎抽象基类"""

    supports_alignment: ClassVar[bool] = False
    fallback_subtitle_characters_per_second: ClassVar[float] = 4.0

    def __init__(self, *, sample_rate: int, channels: int) -> None:
        self._sample_rate = sample_rate
        self._channels = channels

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    def make_fallback_subtitle_output(self, text: str) -> TtsSubtitleOutput | None:
        """为不支持 alignment 的供应商生成固定字符速率时间轴。"""

        if self.supports_alignment or not text:
            return None
        seconds_per_character = 1.0 / self.fallback_subtitle_characters_per_second
        return TtsSubtitleOutput(
            segments=[
                SubtitleSegment(
                    text=character,
                    start=index * seconds_per_character,
                    end=(index + 1) * seconds_per_character,
                )
                for index, character in enumerate(text)
            ]
        )

    @abstractmethod
    def synthesize(self, request: TtsSpeakRequest) -> AsyncGenerator[TtsOutput, None]:
        """根据已校验的发声请求合成音频和可选 alignment 字幕。

        实现为异步生成器;调用方须 aclose(TTSAudioStreamSource 用 aclosing)。
        若引擎内部用 httpx 流,应把连接放在独立任务(见 FishAudioEngine),勿在生成器
        体内 async with 后直接 yield 挂起。
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(sample_rate={self._sample_rate}, channels={self._channels})"

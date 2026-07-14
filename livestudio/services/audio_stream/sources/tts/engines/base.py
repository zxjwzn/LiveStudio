"""TTS 引擎基类:规范各 TTS 供应商接入

引擎按 kind 分发(注册表 ``TTS_ENGINES`` + ``make_engine`` 在 ``engines`` 包)。
各供应商实现 ``synthesize``:输入文本 + 可选 pydantic 请求,流式产出 PCM;
锚点/队列/时钟由呈现层负责,引擎不碰。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel


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
    def synthesize(
        self,
        text: str,
        request: BaseModel | None = None,
    ) -> AsyncGenerator[TtsOutput, None]:
        """合成文本;``request`` 为该供应商的 pydantic 请求模型。

        全局参数(model/latency/speed 等)在连接配置上,不经 request 传入。
        实现为异步生成器;调用方须 aclose(TTSAudioStreamSource 用 aclosing)。
        若引擎内部用 httpx 流,应把连接放在独立任务(见 FishAudioEngine),勿在生成器
        体内 async with 后直接 yield 挂起。
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(sample_rate={self._sample_rate}, channels={self._channels})"

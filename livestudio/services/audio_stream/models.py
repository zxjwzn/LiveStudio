"""通用音频流共享模型。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

import numpy as np
from numpy.typing import NDArray


class AudioSourceKind(StrEnum):
    """音频来源类型。"""

    MICROPHONE = "microphone"
    TTS = "tts"


@dataclass(slots=True)
class AudioChunkMetadata:
    """音频回调附带的时间与状态信息。"""

    input_buffer_adc_time: float | None = None
    current_time: float | None = None
    output_buffer_dac_time: float | None = None
    status: str = ""


@dataclass(slots=True)
class AudioChunk:
    """统一的音频数据块。"""

    frames: int
    samplerate: int
    channels: int
    data: NDArray[np.generic]
    overflowed: bool = False
    metadata: AudioChunkMetadata | None = None


@dataclass(frozen=True, slots=True)
class AudioChunkSubscription:
    """音频块订阅句柄。"""

    id: UUID
    queue: asyncio.Queue[AudioChunk]

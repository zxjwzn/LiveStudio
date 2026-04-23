"""音频输入服务数据模型。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field


class InputDeviceInfo(BaseModel):
    """输入设备信息。"""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, description="设备索引。")
    name: str = Field(min_length=1, description="设备名称。")
    max_input_channels: int = Field(ge=0, description="最大输入声道数。")
    default_samplerate: float = Field(gt=0, description="设备默认采样率。")
    hostapi: int = Field(ge=0, description="所属 Host API 索引。")


@dataclass(slots=True)
class AudioChunk:
    """单次音频回调产生的数据块。"""

    frames: int
    samplerate: int
    channels: int
    data: NDArray[np.generic]
    overflowed: bool = False
    metadata: AudioChunkMetadata | None = None


@dataclass(slots=True)
class AudioChunkMetadata:
    """音频回调附带的时间与状态信息。"""

    input_buffer_adc_time: float | None = None
    current_time: float | None = None
    output_buffer_dac_time: float | None = None
    status: str = ""

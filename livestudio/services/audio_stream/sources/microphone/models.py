"""麦克风音频源数据模型。"""

from __future__ import annotations

from typing import NotRequired, Protocol, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class InputDeviceInfo(BaseModel):
    """输入设备信息。"""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, description="设备索引。")
    name: str = Field(min_length=1, description="设备名称。")
    max_input_channels: int = Field(ge=0, description="最大输入声道数。")
    default_samplerate: float = Field(gt=0, description="设备默认采样率。")
    hostapi: int = Field(ge=0, description="所属 Host API 索引。")


class SoundDeviceTimeInfo(Protocol):
    """sounddevice 回调时间信息协议。"""

    inputBufferAdcTime: float
    currentTime: float
    outputBufferDacTime: float


class RawInputDeviceInfo(TypedDict):
    """sounddevice 输入设备原始信息。"""

    name: str
    max_input_channels: int
    default_samplerate: float | int
    hostapi: int
    index: NotRequired[int]

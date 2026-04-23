"""音频输入服务配置模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AudioInputConfig(BaseModel):
    """麦克风输入配置。"""

    model_config = ConfigDict(extra="forbid")

    device_name: str | None = Field(default=None, description="优先使用的输入设备名称。")
    device_index: int | None = Field(default=None, ge=0, description="优先使用的输入设备索引。")
    samplerate: int | None = Field(default=None, gt=0, description="采样率；为空时使用设备默认值。")
    channels: int = Field(default=1, ge=1, le=32, description="输入声道数。")
    dtype: Literal["float32", "int16", "int32", "uint8"] = Field(default="float32", description="采样数据类型。")
    blocksize: int = Field(default=0, ge=0, description="每次回调的帧数；0 表示由底层自动决定。")
    queue_maxsize: int = Field(default=32, ge=1, le=4096, description="内部音频块缓冲队列大小。")
    latency: Literal["low", "high"] | float | None = Field(default="low", description="输入延迟配置。")

    @model_validator(mode="after")
    def validate_device_selector(self) -> "AudioInputConfig":
        """校验设备选择配置。"""

        if self.device_name is not None and not self.device_name.strip():
            raise ValueError("device_name 不能为空字符串")
        return self

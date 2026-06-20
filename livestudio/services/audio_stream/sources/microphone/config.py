"""麦克风音频源配置模型"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MicrophoneAudioStreamConfig(BaseModel):
    """麦克风输入配置"""

    model_config = ConfigDict(extra="forbid")

    device_name: str | None = Field(
        default=None,
        description="优先使用的输入设备名称",
        json_schema_extra={"gui_label": "输入设备", "gui_widget": "dropdown", "gui_choices_source": "audio.input_devices"},
    )
    device_index: int | None = Field(
        default=None,
        ge=0,
        description="优先使用的输入设备索引",
        json_schema_extra={"gui_hidden": True},  # 由设备名驱动，GUI 不展示索引
    )
    samplerate: int | None = Field(
        default=None,
        gt=0,
        description="采样率；为空时使用设备默认值",
        json_schema_extra={"gui_label": "采样率", "gui_hidden": True},
    )
    channels: int = Field(
        default=1,
        ge=1,
        le=32,
        description="输入声道数",
        json_schema_extra={"gui_label": "声道数", "gui_hidden": True},
    )
    dtype: Literal["float32", "int16", "int32", "uint8"] = Field(
        default="float32",
        description="采样数据类型",
        json_schema_extra={"gui_label": "采样格式", "gui_hidden": True},
    )
    blocksize: int = Field(
        default=0,
        ge=0,
        description="每次回调的帧数；0 表示由底层自动决定",
        json_schema_extra={"gui_label": "块大小", "gui_hidden": True},
    )
    queue_maxsize: int = Field(
        default=32,
        ge=1,
        le=4096,
        description="内部音频块缓冲队列大小",
        json_schema_extra={"gui_label": "缓冲队列", "gui_hidden": True},
    )
    latency: Literal["low", "high"] | float | None = Field(
        default="low",
        description="输入延迟配置",
        json_schema_extra={"gui_label": "延迟", "gui_hidden": True},
    )

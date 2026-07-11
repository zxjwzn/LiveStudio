"""TTS 音频流配置模型(全局:各供应商连接槽并列 + 输出格式)"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .engines.fish_audio import FishAudioConnectionConfig


class TTSAudioStreamConfig(BaseModel):
    """TTS 全局配置:各供应商连接(GUI 全展示) + 采样格式。

    发声参数(音色等)在模型 ``controllers.tts_speak``;本配置只负责「连得上 API」。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SPEAKERS"})

    fish_audio: FishAudioConnectionConfig = Field(
        default_factory=FishAudioConnectionConfig,
        description="Fish Audio 连接(api_key/endpoint)",
    )
    samplerate: int = Field(
        default=24000,
        gt=0,
        description="TTS 输出采样率(idle 静音与引擎共用;sink 会重采样到输出设备)",
        json_schema_extra={"hidden": True},
    )
    channels: int = Field(
        default=1,
        ge=1,
        description="TTS 输出声道数",
        json_schema_extra={"hidden": True},
    )

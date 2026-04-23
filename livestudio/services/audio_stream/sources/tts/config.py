"""TTS 音频流配置模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TTSAudioStreamConfig(BaseModel):
    """TTS 音频流配置占位。"""

    model_config = ConfigDict(extra="forbid")

    stream_url: str | None = Field(default=None, description="TTS 流地址，占位字段。")
    format: str = Field(default="pcm16", description="TTS 流编码格式，占位字段。")
    samplerate: int = Field(default=24000, gt=0, description="TTS 输出采样率，占位字段。")
    channels: int = Field(default=1, ge=1, description="TTS 输出声道数，占位字段。")
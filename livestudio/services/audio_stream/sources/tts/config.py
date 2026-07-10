"""TTS 音频流配置模型"""

from pydantic import BaseModel, ConfigDict, Field

from .engines.fish_audio import FishAudioEngineConfig


class TTSAudioStreamConfig(BaseModel):
    """TTS 音频流配置(引擎 + 输出格式)"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "SPEAKERS"})

    engine: FishAudioEngineConfig = Field(
        default_factory=FishAudioEngineConfig,
        description="TTS 引擎配置(暂时仅 Fish Audio)",
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

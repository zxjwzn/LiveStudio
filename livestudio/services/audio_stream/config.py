"""通用音频流配置模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .models import AudioSourceKind
from .sources.microphone.config import MicrophoneAudioStreamConfig
from .sources.tts.config import TTSAudioStreamConfig


class AudioStreamRouterConfig(BaseModel):
    """音频流路由配置。"""

    model_config = ConfigDict(extra="forbid")

    source: AudioSourceKind = Field(
        default=AudioSourceKind.MICROPHONE,
        description="当前激活的音频源。",
    )
    microphone: MicrophoneAudioStreamConfig = Field(
        default_factory=MicrophoneAudioStreamConfig,
        description="麦克风音频流配置。",
    )
    tts: TTSAudioStreamConfig = Field(
        default_factory=TTSAudioStreamConfig,
        description="TTS 音频流配置。",
    )


class AudioStreamConfigFile(BaseModel):
    """音频流独立配置文件。"""

    model_config = ConfigDict(extra="forbid")

    audio_stream: AudioStreamRouterConfig = Field(
        default_factory=AudioStreamRouterConfig,
    )

"""通用音频流配置模型"""

from pydantic import BaseModel, ConfigDict, Field

from .models import AudioSourceKind
from .playback import PlaybackConfig
from .sources.microphone.config import MicrophoneAudioStreamConfig
from .sources.tts.config import TTSAudioStreamConfig


class AudioStreamRouterConfig(BaseModel):
    """音频流路由配置（即音频流配置文件的根模型，无额外包装层）"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "MEDIA"})

    source: AudioSourceKind = Field(
        default=AudioSourceKind.MICROPHONE,
        description="当前激活的音频源",
    )
    queue_maxsize: int = Field(
        default=32,
        ge=1,
        le=4096,
        description="路由器对活动音频源的转发订阅队列大小（与具体音源无关）",
    )
    microphone: MicrophoneAudioStreamConfig = Field(
        default_factory=MicrophoneAudioStreamConfig,
        description="麦克风音频流配置",
    )
    tts: TTSAudioStreamConfig = Field(
        default_factory=TTSAudioStreamConfig,
        description="TTS 音频流配置",
    )
    playback: PlaybackConfig = Field(
        default_factory=PlaybackConfig,
        description="音频播放订阅方配置（订阅总线、按源过滤后输出到本机设备）",
    )

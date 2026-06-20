"""TTS 音频流源占位实现"""

from ...base import AudioStreamSource
from .config import TTSAudioStreamConfig


class TTSAudioStreamSource(AudioStreamSource):
    """TTS HTTP 流音频源的占位实现"""

    def __init__(self, config: TTSAudioStreamConfig) -> None:
        super().__init__()
        self.config = config

    async def _do_initialize(self) -> None:
        """初始化 TTS 音频流占位资源"""

    async def _do_start(self) -> None:
        """启动 TTS 音频流占位资源"""

    async def _do_stop(self) -> None:
        """停止 TTS 音频流占位资源（释放订阅）"""

        self._clear_subscriptions()

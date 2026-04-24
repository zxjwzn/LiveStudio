"""嘴型同步分析器协议。"""

from __future__ import annotations

from typing import Protocol

from livestudio.services.audio_stream import AudioChunk

from .models import MouthPose


class MouthPoseAnalyzer(Protocol):
    """将音频块转换为嘴型姿态的分析器。"""

    def analyze(self, chunk: AudioChunk) -> MouthPose:
        """分析音频块并返回目标嘴型姿态。"""
        ...

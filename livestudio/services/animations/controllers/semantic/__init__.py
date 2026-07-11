"""这里放各平台都能用的通用动画控制器"""

from .blink import BlinkController
from .breathing import BreathingController
from .expression import ExpressionController
from .gaze import GazeController
from .mouth_expression import MouthExpressionController
from .mouth_sync import MouthSyncController
from .tts_speak import TTSpeakController

__all__ = [
    "BlinkController",
    "BreathingController",
    "ExpressionController",
    "GazeController",
    "MouthExpressionController",
    "MouthSyncController",
    "TTSpeakController",
]

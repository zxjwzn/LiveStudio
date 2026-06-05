"""这里放各平台都能用的通用动画控制器"""

from .blink import BlinkController
from .body_swing import BodySwingController
from .breathing import BreathingController
from .eye_centering import EyeCenteringController
from .mouth_expression import MouthExpressionController
from .mouth_sync import MouthSyncController

__all__ = [
    "BlinkController",
    "BodySwingController",
    "BreathingController",
    "EyeCenteringController",
    "MouthExpressionController",
    "MouthSyncController",
]

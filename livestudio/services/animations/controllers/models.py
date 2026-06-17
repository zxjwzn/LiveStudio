"""动画运行时的数据模型"""

from enum import StrEnum


class AnimationType(StrEnum):
    """动画控制器类型"""

    IDLE = "idle"
    ONESHOT = "oneshot"

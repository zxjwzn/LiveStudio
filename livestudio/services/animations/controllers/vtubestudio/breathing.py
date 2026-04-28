"""VTube Studio 呼吸控制器。"""

from __future__ import annotations

from livestudio.tween import Easing, TweenRequest

from ..base import AnimationController
from ..config import BreathingControllerSettings
from ..models import AnimationType
from .constants import BREATHING_PARAMETER, IDLE_PRIORITY


class BreathingController(AnimationController[BreathingControllerSettings]):
    """通过 FaceAngleY 缓动模拟呼吸。"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次呼吸周期。"""

        await self.runtime.platform.tween.tween(
            TweenRequest(
                parameter_name=BREATHING_PARAMETER,
                end_value=self.config.max_value,
                duration=self.config.inhale_duration,
                easing=Easing.in_out_sine,
                priority=IDLE_PRIORITY,
            ),
        )
        await self.runtime.platform.tween.tween(
            TweenRequest(
                parameter_name=BREATHING_PARAMETER,
                end_value=self.config.min_value,
                duration=self.config.exhale_duration,
                easing=Easing.in_out_sine,
                priority=IDLE_PRIORITY,
            ),
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

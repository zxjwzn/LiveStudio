"""基础呼吸循环控制器。"""

from __future__ import annotations

from ..models import CONTROLLER_PRIORITY, AnimationType, BreathingControllerConfig
from .base import AnimationController


class BreathingController(AnimationController[BreathingControllerConfig]):
    """基础呼吸循环控制器。"""

    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        config = self.config
        await self.runtime.vtubestudio.tween.tween(
            parameter_name=config.parameter,
            end_value=config.max_value,
            duration=config.inhale_duration,
            easing=config.easing,
            priority=CONTROLLER_PRIORITY,
            keep_alive=True,
        )
        await self.runtime.vtubestudio.tween.tween(
            parameter_name=config.parameter,
            end_value=config.min_value,
            duration=config.exhale_duration,
            easing=config.easing,
            priority=CONTROLLER_PRIORITY,
            keep_alive=True,
        )

    async def execute(self, **kwargs: object) -> None:
        _ = kwargs
        await self.run_cycle()

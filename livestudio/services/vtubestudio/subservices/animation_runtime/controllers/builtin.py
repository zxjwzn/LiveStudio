"""内置循环控制器。"""

from __future__ import annotations

import asyncio
import random

from ..models import (
    CONTROLLER_PRIORITY,
    AnimationType,
    BlinkControllerConfig,
    BreathingControllerConfig,
)
from .base import AnimationController


class BlinkController(AnimationController[BlinkControllerConfig]):
    """基础眨眼循环控制器。"""

    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        config = self.config
        await asyncio.gather(
            self.runtime.vtubestudio.tween.tween(
                parameter_name=config.left_parameter,
                end_value=config.closed_value,
                duration=config.close_duration,
                easing=config.easing,
                priority=CONTROLLER_PRIORITY,
                keep_alive=False,
            ),
            self.runtime.vtubestudio.tween.tween(
                parameter_name=config.right_parameter,
                end_value=config.closed_value,
                duration=config.close_duration,
                easing=config.easing,
                priority=CONTROLLER_PRIORITY,
                keep_alive=False,
            ),
        )
        await asyncio.sleep(config.hold_duration)
        await asyncio.gather(
            self.runtime.vtubestudio.tween.tween(
                parameter_name=config.left_parameter,
                end_value=config.open_value,
                duration=config.open_duration,
                easing=config.easing,
                priority=CONTROLLER_PRIORITY,
                keep_alive=False,
            ),
            self.runtime.vtubestudio.tween.tween(
                parameter_name=config.right_parameter,
                end_value=config.open_value,
                duration=config.open_duration,
                easing=config.easing,
                priority=CONTROLLER_PRIORITY,
                keep_alive=False,
            ),
        )
        await asyncio.sleep(random.uniform(config.min_interval, config.max_interval))

    async def execute(self, **kwargs: object) -> None:
        _ = kwargs
        await self.run_cycle()


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

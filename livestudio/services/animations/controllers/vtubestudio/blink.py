"""VTube Studio 眨眼控制器。"""

from __future__ import annotations

import asyncio
import random

from livestudio.log import logger
from livestudio.tween import Easing, TweenRequest

from ..base import AnimationController
from ..config import BlinkControllerSettings
from ..models import AnimationType
from .constants import BLINK_LEFT_PARAMETER, BLINK_RIGHT_PARAMETER, IDLE_PRIORITY


class BlinkController(AnimationController[BlinkControllerSettings]):
    """使用参数缓动实现随机间隔眨眼。"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次眨眼周期。"""

        await asyncio.gather(
            self.runtime.platform.tween.tween(
                TweenRequest(
                    parameter_name=BLINK_LEFT_PARAMETER,
                    end_value=0.0,
                    duration=self.config.close_duration,
                    easing=Easing.in_sine,
                    priority=IDLE_PRIORITY,
                ),
            ),
            self.runtime.platform.tween.tween(
                TweenRequest(
                    parameter_name=BLINK_RIGHT_PARAMETER,
                    end_value=0.0,
                    duration=self.config.close_duration,
                    easing=Easing.in_sine,
                    priority=IDLE_PRIORITY,
                ),
            ),
        )
        await asyncio.sleep(self.config.closed_hold)
        await asyncio.gather(
            self.runtime.platform.tween.tween(
                TweenRequest(
                    parameter_name=BLINK_LEFT_PARAMETER,
                    end_value=1.0,
                    duration=self.config.open_duration,
                    easing=Easing.out_sine,
                    priority=IDLE_PRIORITY,
                ),
            ),
            self.runtime.platform.tween.tween(
                TweenRequest(
                    parameter_name=BLINK_RIGHT_PARAMETER,
                    end_value=1.0,
                    duration=self.config.open_duration,
                    easing=Easing.out_sine,
                    priority=IDLE_PRIORITY,
                ),
            ),
        )

        if self._stop_event.is_set():
            return

        wait_time = random.uniform(
            self.config.min_interval,
            self.config.max_interval,
        )
        logger.debug("下次眨眼等待: {:.2f} 秒", wait_time)
        await asyncio.sleep(wait_time)

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

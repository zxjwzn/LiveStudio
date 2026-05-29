"""VTube Studio 身体摇摆控制器。"""

from __future__ import annotations

import asyncio
import random

from livestudio.tween import Easing, TweenRequest
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import BodySwingControllerSettings
from ..models import AnimationType


class BodySwingController(AnimationController[BodySwingControllerSettings]):
    """通过 FaceAngleX/Z 实现待机身体摇摆。"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次身体摇摆周期。"""

        target_x = random.uniform(self.config.x_min, self.config.x_max)
        target_z = random.uniform(self.config.z_min, self.config.z_max)
        duration = random.uniform(self.config.min_duration, self.config.max_duration)
        easing = random.choice(
            [Easing.in_out_quad, Easing.in_out_back, Easing.in_out_sine],
        )

        logger.debug(
            "身体摇摆: X: {:.2f}, Z: {:.2f}, 时长: {:.2f}s",
            target_x,
            target_z,
            duration,
        )

        requests = [
            TweenRequest(
                parameter_name="FaceAngleX",
                end_value=target_x,
                duration=duration,
                easing=easing,
                priority=10,
            ),
            TweenRequest(
                parameter_name="FaceAngleZ",
                end_value=target_z,
                duration=duration,
                easing=easing,
                priority=10,
            ),
        ]

        await asyncio.gather(
            *(self.runtime.platform.tween.tween(request) for request in requests),
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

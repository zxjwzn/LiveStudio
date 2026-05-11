"""VTube Studio 身体摇摆控制器。"""

from __future__ import annotations

import asyncio
import random

from livestudio.log import logger
from livestudio.tween import EASING_REGISTRY, TweenRequest

from ..base import AnimationController
from ..config import BodySwingControllerSettings
from ..models import AnimationType
from .constants import (
    BODY_SWING_X_PARAMETER,
    BODY_SWING_Z_PARAMETER,
    IDLE_PRIORITY,
)


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
        easing = random.choice(["in_out_quad", "in_out_back", "in_out_sine"])

        logger.debug(
            "身体摇摆: X: {:.2f}, Z: {:.2f}, 时长: {:.2f}s",
            target_x,
            target_z,
            duration,
        )

        requests = [
            TweenRequest(
                parameter_name=BODY_SWING_X_PARAMETER,
                end_value=target_x,
                duration=duration,
                easing=easing,
                priority=IDLE_PRIORITY,
            ),
            TweenRequest(
                parameter_name=BODY_SWING_Z_PARAMETER,
                end_value=target_z,
                duration=duration,
                easing=easing,
                priority=IDLE_PRIORITY,
            ),
        ]

        await asyncio.gather(
            *(self.runtime.platform.tween.tween(request) for request in requests),
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

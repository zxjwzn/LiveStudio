"""VTube Studio 嘴部表情控制器。"""

from __future__ import annotations

import asyncio
import random

from livestudio.log import logger
from livestudio.tween import TweenRequest

from ..base import AnimationController
from ..config import MouthExpressionControllerSettings
from ..models import AnimationType
from .constants import IDLE_PRIORITY, MOUTH_OPEN_PARAMETER, MOUTH_SMILE_PARAMETER


class MouthExpressionController(AnimationController[MouthExpressionControllerSettings]):
    """随机改变微笑和嘴巴张开程度，增加待机生动性。"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次嘴部表情变化周期。"""

        target_smile = random.uniform(self.config.smile_min, self.config.smile_max)
        target_open = random.uniform(self.config.open_min, self.config.open_max)
        duration = random.uniform(self.config.min_duration, self.config.max_duration)
        easing = random.choice(["in_out_quad", "in_out_back", "in_out_sine"])

        logger.debug(
            "嘴部表情: Smile: {:.2f}, Open: {:.2f}, 时长: {:.2f}s, 缓动: {}",
            target_smile,
            target_open,
            duration,
            easing,
        )

        await asyncio.gather(
            self.runtime.platform.tween.tween(
                TweenRequest(
                    parameter_name=MOUTH_SMILE_PARAMETER,
                    end_value=target_smile,
                    duration=duration,
                    easing=easing,
                    priority=IDLE_PRIORITY,
                ),
            ),
            self.runtime.platform.tween.tween(
                TweenRequest(
                    parameter_name=MOUTH_OPEN_PARAMETER,
                    end_value=target_open,
                    duration=duration,
                    easing=easing,
                    priority=IDLE_PRIORITY,
                ),
            ),
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

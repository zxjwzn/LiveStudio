"""Platform-independent semantic blink controller."""

from __future__ import annotations

import asyncio
import random

from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionTarget,
    SemanticTweenRequest,
)
from livestudio.tween import Easing
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import BlinkControllerSettings
from ..models import AnimationType


class BlinkController(AnimationController[BlinkControllerSettings]):
    """使用眼睛闭合语义动作实现随机间隔眨眼。"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次眨眼周期。"""

        await self.runtime.platform.tween_semantic(
            SemanticTweenRequest(
                targets=(SemanticActionTarget(SemanticAction.EYE_CLOSE.value, 1.0),),
                duration=self.config.close_duration,
                easing=Easing.in_sine,
                priority=10,
            ),
        )
        await asyncio.sleep(self.config.closed_hold)

        await self.runtime.platform.tween_semantic(
            SemanticTweenRequest(
                targets=(SemanticActionTarget(SemanticAction.EYE_CLOSE.value, 0.0),),
                duration=self.config.open_duration,
                easing=Easing.out_sine,
                priority=10,
            ),
        )
        wait_time = random.uniform(
            self.config.min_interval,
            self.config.max_interval,
        )
        logger.debug("下次眨眼等待: {:.2f} 秒", wait_time)
        await asyncio.sleep(wait_time)

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

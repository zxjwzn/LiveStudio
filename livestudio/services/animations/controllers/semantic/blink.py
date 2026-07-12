"""各平台都能用的眨眼控制器"""

import asyncio
import random

from livestudio.services.semantic_actions import SemanticAction, SemanticTweenRequest
from livestudio.services.tween import Easing
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import BlinkControllerSettings
from ..constants import IDLE_CONTROLLER_PRIORITY
from ..models import AnimationType


class BlinkController(AnimationController[BlinkControllerSettings]):
    """使用眼睛开合语义动作实现随机间隔眨眼"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次眨眼周期"""

        await self.runtime.platform.tween_semantic(
            [
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.EYE_OPEN,
                    end_value=0.0,
                    duration=self.config.close_duration,
                    easing=Easing.out_sine,
                    priority=IDLE_CONTROLLER_PRIORITY,
                ),
            ],
        )
        await asyncio.sleep(self.config.closed_hold)

        await self.runtime.platform.tween_semantic(
            [
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.EYE_OPEN,
                    end_value=1.0,
                    duration=self.config.open_duration,
                    easing=Easing.out_sine,
                    priority=IDLE_CONTROLLER_PRIORITY,
                ),
            ],
        )
        wait_time = random.uniform(
            self.config.min_interval,
            self.config.max_interval,
        )
        logger.debug("下次眨眼等待: {:.2f} 秒", wait_time)
        await asyncio.sleep(wait_time)

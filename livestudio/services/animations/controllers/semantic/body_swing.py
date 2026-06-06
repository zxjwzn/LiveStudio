"""各平台都能用的身体摆动控制器"""

from __future__ import annotations

import random

from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionTarget,
    SemanticTweenRequest,
)
from livestudio.tween import Easing
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import BodySwingControllerSettings
from ..models import AnimationType


class BodySwingController(AnimationController[BodySwingControllerSettings]):
    """通过头部偏转/侧倾语义动作实现待机身体摇摆"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次身体摇摆周期"""

        target_yaw = random.uniform(
            -self.config.yaw_amplitude,
            self.config.yaw_amplitude,
        )
        target_roll = random.uniform(
            -self.config.roll_amplitude,
            self.config.roll_amplitude,
        )
        duration = random.uniform(self.config.min_duration, self.config.max_duration)
        easing = random.choice(
            [Easing.in_out_quad, Easing.in_out_back, Easing.in_out_sine],
        )

        logger.debug(
            "身体摇摆: yaw: {:.2f}, roll: {:.2f}, 时长: {:.2f}s",
            target_yaw,
            target_roll,
            duration,
        )

        current_yaw = await self.runtime.get_semantic_value(
            SemanticAction.HEAD_YAW.value,
        )
        current_roll = await self.runtime.get_semantic_value(
            SemanticAction.HEAD_ROLL.value,
        )

        await self.runtime.platform.tween_semantic(
            SemanticTweenRequest(
                targets=(
                    SemanticActionTarget(
                        SemanticAction.HEAD_YAW.value,
                        target_yaw,
                        start_value=current_yaw.value
                        if current_yaw is not None
                        else None,
                    ),
                    SemanticActionTarget(
                        SemanticAction.HEAD_ROLL.value,
                        target_roll,
                        start_value=(
                            current_roll.value if current_roll is not None else None
                        ),
                    ),
                ),
                duration=duration,
                easing=easing,
                priority=10,
            ),
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画"""

        _ = kwargs

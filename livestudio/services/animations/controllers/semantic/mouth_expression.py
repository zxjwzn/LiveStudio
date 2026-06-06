"""各平台都能用的嘴部表情控制器"""

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
from ..config import MouthExpressionControllerSettings
from ..models import AnimationType


class MouthExpressionController(AnimationController[MouthExpressionControllerSettings]):
    """随机改变嘴角上扬语义强度，增加待机生动性"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次嘴部表情变化周期"""

        target_smile = random.uniform(0.0, self.config.smile_amplitude)
        duration = random.uniform(self.config.min_duration, self.config.max_duration)
        easing = random.choice(
            [Easing.in_out_quad, Easing.in_out_back, Easing.in_out_sine],
        )

        logger.debug(
            "嘴部表情: Smile: {:.2f}, 时长: {:.2f}s, 缓动: {}",
            target_smile,
            duration,
            easing,
        )

        current_smile = await self.runtime.get_semantic_value(
            SemanticAction.MOUTH_SMILE.value,
        )
        target = SemanticActionTarget(
            SemanticAction.MOUTH_SMILE.value,
            target_smile,
            start_value=current_smile.value if current_smile is not None else None,
        )
        await self.runtime.platform.tween_semantic(
            SemanticTweenRequest(
                targets=(target,),
                duration=duration,
                easing=easing,
                priority=10,
            ),
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画"""

        _ = kwargs

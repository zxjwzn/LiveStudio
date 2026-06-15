"""各平台都能用的呼吸控制器"""

from __future__ import annotations

from livestudio.services.semantic_actions import SemanticAction, SemanticTweenRequest
from livestudio.services.tween import Easing

from ..base import AnimationController
from ..config import BreathingControllerSettings
from ..models import AnimationType


class BreathingController(AnimationController[BreathingControllerSettings]):
    """通过头部俯仰语义动作模拟呼吸"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次呼吸周期"""

        await self.runtime.platform.tween_semantic(
            [
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.HEAD_PITCH,
                    end_value=self.config.pitch_amplitude,
                    duration=self.config.inhale_duration,
                    easing=Easing.in_out_sine,
                    priority=10,
                ),
            ],
        )
        await self.runtime.platform.tween_semantic(
            [
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.HEAD_PITCH,
                    end_value=-self.config.pitch_amplitude,
                    duration=self.config.exhale_duration,
                    easing=Easing.in_out_sine,
                    priority=10,
                ),
            ],
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画"""

        _ = kwargs

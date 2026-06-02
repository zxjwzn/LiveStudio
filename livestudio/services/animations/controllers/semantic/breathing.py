"""Platform-independent semantic breathing controller."""

from __future__ import annotations

from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionTarget,
    SemanticTweenRequest,
)
from livestudio.tween import Easing

from ..base import AnimationController
from ..config import BreathingControllerSettings
from ..models import AnimationType


class BreathingController(AnimationController[BreathingControllerSettings]):
    """通过头部俯仰语义动作模拟呼吸。"""

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次呼吸周期。"""

        current_pitch = await self.runtime.get_semantic_value(
            SemanticAction.HEAD_PITCH.value,
        )
        await self.runtime.platform.tween_semantic(
            SemanticTweenRequest(
                targets=(
                    SemanticActionTarget(
                        SemanticAction.HEAD_PITCH.value,
                        self.config.pitch_amplitude,
                        start_value=(
                            current_pitch.value if current_pitch is not None else None
                        ),
                    ),
                ),
                duration=self.config.inhale_duration,
                easing=Easing.in_out_sine,
                priority=10,
            ),
        )
        current_pitch = await self.runtime.get_semantic_value(
            SemanticAction.HEAD_PITCH.value,
        )
        await self.runtime.platform.tween_semantic(
            SemanticTweenRequest(
                targets=(
                    SemanticActionTarget(
                        SemanticAction.HEAD_PITCH.value,
                        -self.config.pitch_amplitude,
                        start_value=(
                            current_pitch.value if current_pitch is not None else None
                        ),
                    ),
                ),
                duration=self.config.exhale_duration,
                easing=Easing.in_out_sine,
                priority=10,
            ),
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

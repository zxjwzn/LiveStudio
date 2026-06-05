"""让眼睛保持居中的补偿控制器"""

from __future__ import annotations

import asyncio

from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticActionState,
    SemanticActionTarget,
    SemanticTweenRequest,
)
from livestudio.tween import Easing

from ..base import AnimationController
from ..config import EyeCenteringControllerSettings
from ..models import AnimationType


class EyeCenteringController(AnimationController[EyeCenteringControllerSettings]):
    """根据头部姿势反向调整视线，让瞳孔看起来保持在中间"""

    def __init__(
        self,
        runtime,
        name: str,
        config: EyeCenteringControllerSettings,
    ) -> None:
        super().__init__(runtime, name, config)
        self._current_x = 0.0
        self._current_y = 0.0

    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        yaw = await self.runtime.get_semantic_value(SemanticAction.HEAD_YAW.value)
        pitch = await self.runtime.get_semantic_value(SemanticAction.HEAD_PITCH.value)
        roll = await self.runtime.get_semantic_value(SemanticAction.HEAD_ROLL.value)

        target_x, target_y = self._compute_centering(yaw, pitch, roll)
        smoothed_x = self._smooth(self._current_x, target_x)
        smoothed_y = self._smooth(self._current_y, target_y)
        if self._is_within_deadzone(smoothed_x, self._current_x) and self._is_within_deadzone(
            smoothed_y,
            self._current_y,
        ):
            await asyncio.sleep(self.config.update_interval)
            return

        previous_x = self._current_x
        previous_y = self._current_y
        self._current_x = smoothed_x
        self._current_y = smoothed_y

        await self.runtime.platform.tween_semantic(
            SemanticTweenRequest(
                targets=(
                    SemanticActionTarget(
                        SemanticAction.EYE_GAZE_X.value,
                        smoothed_x,
                        start_value=previous_x,
                    ),
                    SemanticActionTarget(
                        SemanticAction.EYE_GAZE_Y.value,
                        smoothed_y,
                        start_value=previous_y,
                    ),
                ),
                duration=self.config.duration,
                easing=Easing.out_sine,
                priority=self.config.priority,
                keep_alive=True,
            ),
        )
        await asyncio.sleep(self.config.update_interval)

    async def execute(self, **kwargs: object) -> None:
        _ = kwargs

    def _compute_centering(
        self,
        yaw: SemanticActionState | None,
        pitch: SemanticActionState | None,
        roll: SemanticActionState | None,
    ) -> tuple[float, float]:
        yaw_value = yaw.value if yaw is not None else 0.0
        pitch_value = pitch.value if pitch is not None else 0.0
        roll_value = roll.value if roll is not None else 0.0
        return (
            self._clamp_unit(
                -yaw_value * self.config.yaw_compensation
                - roll_value * self.config.roll_to_x_compensation,
            ),
            self._clamp_unit(
                -pitch_value * self.config.pitch_compensation
                - roll_value * self.config.roll_to_y_compensation,
            ),
        )

    def _smooth(self, current: float, target: float) -> float:
        smoothing = self.config.smoothing
        if smoothing <= 0.0:
            return self._clamp_unit(target)
        return self._clamp_unit(current + (target - current) * smoothing)

    def _is_within_deadzone(self, value: float, previous: float) -> bool:
        return abs(value - previous) <= self.config.deadzone

    @staticmethod
    def _clamp_unit(value: float) -> float:
        return max(-1.0, min(1.0, value))

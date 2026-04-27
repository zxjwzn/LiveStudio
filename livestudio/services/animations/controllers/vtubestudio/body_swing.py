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
    EYE_LEFT_X_PARAMETER,
    EYE_LEFT_Y_PARAMETER,
    EYE_RIGHT_X_PARAMETER,
    EYE_RIGHT_Y_PARAMETER,
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
        easing = random.choice(tuple(EASING_REGISTRY.values()))

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
            ),
            TweenRequest(
                parameter_name=BODY_SWING_Z_PARAMETER,
                end_value=target_z,
                duration=duration,
                easing=easing,
            ),
        ]

        if self.config.eye_follow.enabled:
            eye_x, eye_y = self._resolve_eye_target(target_x, target_z)
            logger.debug("眼睛跟随: 目标=({:.2f}, {:.2f})", eye_x, eye_y)
            requests.extend(
                [
                    TweenRequest(
                        parameter_name=EYE_LEFT_X_PARAMETER,
                        end_value=eye_x,
                        duration=duration,
                        easing=easing,
                    ),
                    TweenRequest(
                        parameter_name=EYE_RIGHT_X_PARAMETER,
                        end_value=eye_x,
                        duration=duration,
                        easing=easing,
                    ),
                    TweenRequest(
                        parameter_name=EYE_LEFT_Y_PARAMETER,
                        end_value=eye_y,
                        duration=duration,
                        easing=easing,
                    ),
                    TweenRequest(
                        parameter_name=EYE_RIGHT_Y_PARAMETER,
                        end_value=eye_y,
                        duration=duration,
                        easing=easing,
                    ),
                ],
            )

        await asyncio.gather(
            *(self.runtime.platform.tween.tween(request) for request in requests),
        )

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

    def _resolve_eye_target(
        self,
        target_x: float,
        target_z: float,
    ) -> tuple[float, float]:
        eye_config = self.config.eye_follow
        x_range = self.config.x_max - self.config.x_min
        x_norm = (target_x - self.config.x_min) / x_range if x_range else 0.0
        eye_x = eye_config.x_min_range + x_norm * (
            eye_config.x_max_range - eye_config.x_min_range
        )

        z_range = self.config.z_max - self.config.z_min
        z_norm = (target_z - self.config.z_min) / z_range if z_range else 0.0
        eye_y = eye_config.y_max_range - z_norm * (
            eye_config.y_max_range - eye_config.y_min_range
        )
        return eye_x, eye_y

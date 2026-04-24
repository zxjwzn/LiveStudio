"""嘴型姿态平滑器。"""

from __future__ import annotations

from ..models import MouthSyncControllerConfig
from .models import MouthPose


class MouthPoseSmoother:
    """按维度平滑嘴型姿态。"""

    def __init__(
        self,
        initial_pose: MouthPose,
        config: MouthSyncControllerConfig,
    ) -> None:
        self._pose = initial_pose.clamp()
        self._config = config

    @property
    def current_pose(self) -> MouthPose:
        """返回当前平滑后的姿态。"""

        return self._pose

    def smooth(self, target_pose: MouthPose) -> MouthPose:
        """将目标姿态平滑到当前姿态。"""

        target = target_pose.clamp()
        self._pose = MouthPose(
            open=self._lerp(self._pose.open, target.open, self._config.open_smoothing),
            smile=self._lerp(
                self._pose.smile,
                target.smile,
                self._config.smile_smoothing,
            ),
            x=self._lerp(self._pose.x, target.x, self._config.x_smoothing),
        ).clamp()
        return self._pose

    @staticmethod
    def _lerp(start: float, end: float, factor: float) -> float:
        return start + (end - start) * factor

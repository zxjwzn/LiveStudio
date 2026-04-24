"""嘴型姿态到 VTS 参数的映射。"""

from __future__ import annotations

from ..models import MouthSyncControllerConfig
from .models import MouthPose


class MouthPoseParameterMapper:
    """将嘴型姿态转换为 VTube Studio 参数值。"""

    def __init__(self, config: MouthSyncControllerConfig) -> None:
        self._config = config

    @property
    def parameter_names(self) -> tuple[str, ...]:
        """返回当前映射会控制的参数名。"""

        names = [self._config.parameters.open]
        if self._config.parameters.smile is not None:
            names.append(self._config.parameters.smile)
        if self._config.parameters.x is not None:
            names.append(self._config.parameters.x)
        return tuple(names)

    def to_values(self, pose: MouthPose) -> dict[str, float]:
        """生成可直接写入缓动引擎的参数值。"""

        clamped_pose = pose.clamp()
        values = {self._config.parameters.open: clamped_pose.open}
        if self._config.parameters.smile is not None:
            values[self._config.parameters.smile] = clamped_pose.smile
        if self._config.parameters.x is not None:
            values[self._config.parameters.x] = clamped_pose.x
        return values

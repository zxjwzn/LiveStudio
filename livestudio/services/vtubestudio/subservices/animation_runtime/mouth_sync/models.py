"""嘴型同步内部模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MouthPose:
    """归一化嘴型姿态。"""

    open: float
    smile: float
    x: float

    def clamp(self) -> MouthPose:
        """限制到 VTube Studio 参数安全范围。"""

        return MouthPose(
            open=max(0.0, min(1.0, self.open)),
            smile=max(0.0, min(1.0, self.smile)),
            x=max(-1.0, min(1.0, self.x)),
        )

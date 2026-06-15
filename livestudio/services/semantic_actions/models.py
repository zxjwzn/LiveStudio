"""这些是各平台都能用的脸部动作说法"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.tween import EasingFunction


@runtime_checkable
class _HasActionWeight(Protocol):
    @property
    def action(self) -> str: ...
    @property
    def weight(self) -> float: ...


class FacialRegion(StrEnum):
    """脸部动作相关的区域分类"""

    BROW = "brow"
    EYE = "eye"
    MOUTH = "mouth"
    HEAD = "head"


class SemanticAction(StrEnum):
    """这些是各平台都能认的脸和头部动作名字"""

    BROW_HEIGHT = "brow.height"
    EYE_OPEN = "eye.open"
    EYE_GAZE_X = "eye.gaze.x"
    EYE_GAZE_Y = "eye.gaze.y"
    MOUTH_OPEN = "mouth.open"
    MOUTH_SMILE = "mouth.smile"
    MOUTH_X = "mouth.x"
    MOUTH_Y = "mouth.y"
    HEAD_YAW = "head.yaw"
    HEAD_PITCH = "head.pitch"
    HEAD_ROLL = "head.roll"


class PlatformParameterSpec(BaseModel):
    """这里记录平台参数能用的数值范围"""

    model_config = ConfigDict(extra="forbid")

    name: str
    minimum: float
    maximum: float


class SemanticActionBinding(BaseModel):
    """这里说明一个通用动作对应哪些平台参数"""

    model_config = ConfigDict(extra="forbid")

    action: str
    platform_params: list[str]
    curve: str = "linear"


class SemanticActionProfile(BaseModel):
    """这里放通用动作到平台参数的对应关系"""

    model_config = ConfigDict(extra="forbid")

    bindings: list[SemanticActionBinding] = Field(
        default_factory=list,
        description="通用动作到平台参数的对应关系",
    )

    def supports(self, action: str) -> bool:
        """检查是否有绑定覆盖指定的语义动作"""
        return any(binding.action == action for binding in self.bindings)

    def support_score(self, targets: Iterable[_HasActionWeight]) -> float:
        """计算一组目标被当前绑定覆盖的加权比例 (0.0 ~ 1.0)"""
        target_tuple = tuple(targets)
        if not target_tuple:
            return 1.0
        total_weight = sum(max(0.0, t.weight) for t in target_tuple)
        if total_weight <= 0.0:
            return 0.0
        score = sum(
            max(0.0, t.weight) for t in target_tuple if self.supports(t.action)
        )
        return max(0.0, min(1.0, score / total_weight))


@dataclass(frozen=True, slots=True)
class SemanticActionSpec:
    """这里写一个动作能用的数值范围"""

    id: SemanticAction
    minimum: float
    maximum: float
    region: FacialRegion
    description: str = ""


DEFAULT_SEMANTIC_ACTION_SPECS: list[SemanticActionSpec] = [
    SemanticActionSpec(
        id=SemanticAction.BROW_HEIGHT,
        minimum=0.0,
        maximum=1.0,
        region=FacialRegion.BROW,
        description="眉毛从低到高的程度",
    ),
    SemanticActionSpec(
        id=SemanticAction.EYE_OPEN,
        minimum=0.0,
        maximum=1.0,
        region=FacialRegion.EYE,
        description="眼睛从闭上到睁大的程度",
    ),
    SemanticActionSpec(
        id=SemanticAction.EYE_GAZE_X,
        minimum=-1.0,
        maximum=1.0,
        region=FacialRegion.EYE,
        description="眼睛左右看的方向",
    ),
    SemanticActionSpec(
        id=SemanticAction.EYE_GAZE_Y,
        minimum=-1.0,
        maximum=1.0,
        region=FacialRegion.EYE,
        description="眼睛上下看的方向",
    ),
    SemanticActionSpec(
        id=SemanticAction.MOUTH_OPEN,
        minimum=0.0,
        maximum=1.0,
        region=FacialRegion.MOUTH,
        description="嘴巴张开的程度",
    ),
    SemanticActionSpec(
        id=SemanticAction.MOUTH_SMILE,
        minimum=0.0,
        maximum=1.0,
        region=FacialRegion.MOUTH,
        description="嘴角往上扬的程度",
    ),
    SemanticActionSpec(
        id=SemanticAction.MOUTH_X,
        minimum=-1.0,
        maximum=1.0,
        region=FacialRegion.MOUTH,
        description="嘴部左右移动的位置",
    ),
    SemanticActionSpec(
        id=SemanticAction.MOUTH_Y,
        minimum=-1.0,
        maximum=1.0,
        region=FacialRegion.MOUTH,
        description="嘴部上下移动的位置",
    ),
    SemanticActionSpec(
        id=SemanticAction.HEAD_YAW,
        minimum=-1.0,
        maximum=1.0,
        region=FacialRegion.HEAD,
        description="头往左或往右转的程度",
    ),
    SemanticActionSpec(
        id=SemanticAction.HEAD_PITCH,
        minimum=-1.0,
        maximum=1.0,
        region=FacialRegion.HEAD,
        description="头往上或往下抬的程度",
    ),
    SemanticActionSpec(
        id=SemanticAction.HEAD_ROLL,
        minimum=-1.0,
        maximum=1.0,
        region=FacialRegion.HEAD,
        description="头往左或往右歪的程度",
    ),
]


@dataclass(frozen=True, slots=True)
class SemanticTweenRequest:
    """这里用通用动作来描述一次平滑变化请求"""

    action_parameter_name: str
    end_value: float
    duration: float
    easing: str | EasingFunction
    start_value: float | None = None
    delay: float = 0.0
    mode: Literal["set", "add"] = "set"
    fps: int = 60
    priority: int = 0
    keep_alive: bool = True


# 按 action id 查找的字典
_SPEC_BY_ACTION: dict[str, SemanticActionSpec] = {
    spec.id: spec for spec in DEFAULT_SEMANTIC_ACTION_SPECS
}


def clamp_semantic_value(action: str, value: float) -> float:
    """把值钳位到语义动作的合法范围"""
    spec = _SPEC_BY_ACTION.get(action)
    if spec is None:
        return max(-1.0, min(1.0, value))
    return max(spec.minimum, min(spec.maximum, value))

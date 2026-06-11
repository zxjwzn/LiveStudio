"""这些是各平台都能用的脸部动作说法"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from livestudio.services.tween import EasingFunction


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


@dataclass(frozen=True, slots=True)
class SemanticActionSpec:
    """这里写一个动作能用的数值范围"""

    id: str
    minimum: float
    maximum: float
    neutral: float
    default: float
    region: str
    description: str = ""


DEFAULT_SEMANTIC_ACTION_SPECS: dict[str, SemanticActionSpec] = {
    SemanticAction.BROW_HEIGHT.value: SemanticActionSpec(
        id=SemanticAction.BROW_HEIGHT.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.5,
        default=0.5,
        region="brow",
        description="眉毛从低到高的程度",
    ),
    SemanticAction.EYE_OPEN.value: SemanticActionSpec(
        id=SemanticAction.EYE_OPEN.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.75,
        default=1.0,
        region="eye",
        description="眼睛从闭上到睁大的程度",
    ),
    SemanticAction.EYE_GAZE_X.value: SemanticActionSpec(
        id=SemanticAction.EYE_GAZE_X.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="eye",
        description="眼睛左右看的方向",
    ),
    SemanticAction.EYE_GAZE_Y.value: SemanticActionSpec(
        id=SemanticAction.EYE_GAZE_Y.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="eye",
        description="眼睛上下看的方向",
    ),
    SemanticAction.MOUTH_OPEN.value: SemanticActionSpec(
        id=SemanticAction.MOUTH_OPEN.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="mouth",
        description="嘴巴张开的程度",
    ),
    SemanticAction.MOUTH_SMILE.value: SemanticActionSpec(
        id=SemanticAction.MOUTH_SMILE.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="mouth",
        description="嘴角往上扬的程度",
    ),
    SemanticAction.MOUTH_X.value: SemanticActionSpec(
        id=SemanticAction.MOUTH_X.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="mouth",
        description="嘴部左右移动的位置",
    ),
    SemanticAction.MOUTH_Y.value: SemanticActionSpec(
        id=SemanticAction.MOUTH_Y.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="mouth",
        description="嘴部上下移动的位置",
    ),
    SemanticAction.HEAD_YAW.value: SemanticActionSpec(
        id=SemanticAction.HEAD_YAW.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="head",
        description="头往左或往右转的程度",
    ),
    SemanticAction.HEAD_PITCH.value: SemanticActionSpec(
        id=SemanticAction.HEAD_PITCH.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="head",
        description="头往上或往下抬的程度",
    ),
    SemanticAction.HEAD_ROLL.value: SemanticActionSpec(
        id=SemanticAction.HEAD_ROLL.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="head",
        description="头往左或往右歪的程度",
    ),
}


@dataclass(frozen=True, slots=True)
class SemanticActionTarget:
    """这里表示一个动作要动到什么值"""

    action: str
    value: float
    weight: float = 1.0
    start_value: float | None = None


@dataclass(frozen=True, slots=True)
class SemanticTweenRequest:
    """这里用通用动作来描述一次平滑变化请求"""

    targets: tuple[SemanticActionTarget, ...]
    duration: float
    easing: str | EasingFunction
    priority: int = 0
    delay: float = 0.0
    mode: Literal["set", "add"] = "set"
    fps: int = 60
    keep_alive: bool = True


def clamp_semantic_value(action: str, value: float) -> float:
    """把动作数值限制在允许范围里"""

    spec = DEFAULT_SEMANTIC_ACTION_SPECS.get(action)
    if spec is None:
        return max(-1.0, min(1.0, value))
    return max(spec.minimum, min(spec.maximum, value))

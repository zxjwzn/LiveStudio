"""Platform-independent facial action semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from livestudio.tween import EasingFunction


class SemanticAction(StrEnum):
    """Platform-independent facial and head action identifiers."""

    BROW_RAISE = "brow.raise"
    BROW_LOWER = "brow.lower"
    EYE_CLOSE = "eye.close"
    EYE_WIDEN = "eye.widen"
    MOUTH_OPEN = "mouth.open"
    MOUTH_SMILE = "mouth.smile"
    MOUTH_FROWN = "mouth.frown"
    HEAD_YAW = "head.yaw"
    HEAD_PITCH = "head.pitch"
    HEAD_ROLL = "head.roll"


@dataclass(frozen=True, slots=True)
class SemanticActionSpec:
    """Declared normalized range for one semantic action."""

    id: str
    minimum: float
    maximum: float
    neutral: float
    default: float
    region: str
    description: str = ""


DEFAULT_SEMANTIC_ACTION_SPECS: dict[str, SemanticActionSpec] = {
    SemanticAction.BROW_RAISE.value: SemanticActionSpec(
        id=SemanticAction.BROW_RAISE.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="brow",
        description="Raise brows.",
    ),
    SemanticAction.BROW_LOWER.value: SemanticActionSpec(
        id=SemanticAction.BROW_LOWER.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="brow",
        description="Lower brows.",
    ),
    SemanticAction.EYE_CLOSE.value: SemanticActionSpec(
        id=SemanticAction.EYE_CLOSE.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="eye",
        description="Close eyelids.",
    ),
    SemanticAction.EYE_WIDEN.value: SemanticActionSpec(
        id=SemanticAction.EYE_WIDEN.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="eye",
        description="Open eyes wider than neutral.",
    ),
    SemanticAction.MOUTH_OPEN.value: SemanticActionSpec(
        id=SemanticAction.MOUTH_OPEN.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="mouth",
        description="Open mouth.",
    ),
    SemanticAction.MOUTH_SMILE.value: SemanticActionSpec(
        id=SemanticAction.MOUTH_SMILE.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="mouth",
        description="Raise mouth corners.",
    ),
    SemanticAction.MOUTH_FROWN.value: SemanticActionSpec(
        id=SemanticAction.MOUTH_FROWN.value,
        minimum=0.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="mouth",
        description="Lower mouth corners.",
    ),
    SemanticAction.HEAD_YAW.value: SemanticActionSpec(
        id=SemanticAction.HEAD_YAW.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="head",
        description="Turn head left or right.",
    ),
    SemanticAction.HEAD_PITCH.value: SemanticActionSpec(
        id=SemanticAction.HEAD_PITCH.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="head",
        description="Tilt head up or down.",
    ),
    SemanticAction.HEAD_ROLL.value: SemanticActionSpec(
        id=SemanticAction.HEAD_ROLL.value,
        minimum=-1.0,
        maximum=1.0,
        neutral=0.0,
        default=0.0,
        region="head",
        description="Roll head left or right.",
    ),
}


@dataclass(frozen=True, slots=True)
class SemanticActionTarget:
    """A normalized semantic action target."""

    action: str
    value: float
    weight: float = 1.0
    start_value: float | None = None


@dataclass(frozen=True, slots=True)
class SemanticTweenRequest:
    """A tween request expressed in platform-independent semantic actions."""

    targets: tuple[SemanticActionTarget, ...]
    duration: float
    easing: str | EasingFunction
    priority: int = 0
    delay: float = 0.0
    mode: Literal["set", "add"] = "set"
    fps: int = 60
    keep_alive: bool = True


def clamp_semantic_value(action: str, value: float) -> float:
    """Clamp a normalized action value to the declared semantic range."""

    spec = DEFAULT_SEMANTIC_ACTION_SPECS.get(action)
    if spec is None:
        return max(-1.0, min(1.0, value))
    return max(spec.minimum, min(spec.maximum, value))

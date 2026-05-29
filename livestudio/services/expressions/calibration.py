"""Expression calibration from semantic parameters to VTS parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from livestudio.tween import ControlledParameterState

from .models import ExpressionUnit, SemanticParameter

CalibrationCurve = Literal["linear", "ease_in", "ease_out", "ease_in_out"]


@dataclass(frozen=True, slots=True)
class ResolvedExpressionParameter:
    """Resolved VTS parameter value with a calibrated fallback start value."""

    name: str
    value: float
    start_value: float
    mode: Literal["set", "add"] = "set"
    keep_alive: bool = True


@dataclass(frozen=True, slots=True)
class VTubeStudioParameterRange:
    """Default VTS tracking parameter bounds."""

    minimum: float
    maximum: float
    default: float


VTS_DEFAULT_TRACKING_PARAMETER_RANGES: dict[str, VTubeStudioParameterRange] = {
    "FacePositionX": VTubeStudioParameterRange(-15.0, 15.0, 0.0),
    "FacePositionY": VTubeStudioParameterRange(-15.0, 15.0, 0.0),
    "FacePositionZ": VTubeStudioParameterRange(-10.0, 10.0, 0.0),
    "FaceAngleX": VTubeStudioParameterRange(-30.0, 30.0, 0.0),
    "FaceAngleY": VTubeStudioParameterRange(-30.0, 30.0, 0.0),
    "FaceAngleZ": VTubeStudioParameterRange(-90.0, 90.0, 0.0),
    "MouthSmile": VTubeStudioParameterRange(0.0, 1.0, 0.0),
    "MouthOpen": VTubeStudioParameterRange(0.0, 1.0, 0.0),
    "Brows": VTubeStudioParameterRange(0.0, 1.0, 0.0),
    "BrowLeftY": VTubeStudioParameterRange(0.0, 1.0, 0.0),
    "BrowRightY": VTubeStudioParameterRange(0.0, 1.0, 0.0),
    "EyeOpenLeft": VTubeStudioParameterRange(0.0, 1.0, 0.0),
    "EyeOpenRight": VTubeStudioParameterRange(0.0, 1.0, 0.0),
    "EyeLeftX": VTubeStudioParameterRange(-1.0, 1.0, 0.0),
    "EyeLeftY": VTubeStudioParameterRange(-1.0, 1.0, 0.0),
    "EyeRightX": VTubeStudioParameterRange(-1.0, 1.0, 0.0),
    "EyeRightY": VTubeStudioParameterRange(-1.0, 1.0, 0.0),
    "MousePositionX": VTubeStudioParameterRange(-1.0, 1.0, 0.0),
    "MousePositionY": VTubeStudioParameterRange(-1.0, 1.0, 0.0),
    "MouthX": VTubeStudioParameterRange(-1.0, 1.0, 0.0),
}


class SemanticParameterCalibration(BaseModel):
    """Mapping for one semantic parameter on one VTube Studio model."""

    model_config = ConfigDict(extra="forbid")

    semantic_param: str = Field(min_length=1)
    vts_params: list[str] = Field(min_length=1)
    neutral: float = 0.0
    negative_limit: float = -1.0
    positive_limit: float = 1.0
    inverted: bool = False
    curve: CalibrationCurve = "linear"
    enabled: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_limits(self) -> SemanticParameterCalibration:
        if self.negative_limit > self.neutral:
            raise ValueError("negative_limit cannot be greater than neutral")
        if self.positive_limit < self.neutral:
            raise ValueError("positive_limit cannot be less than neutral")
        return self


class CalibrationProfile(BaseModel):
    """Per-model semantic expression calibration profile."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = ""
    model_name: str = ""
    parameters: dict[str, SemanticParameterCalibration] = Field(
        default_factory=dict,
        description="Semantic parameter name to VTS parameter calibration.",
    )

    @classmethod
    def with_defaults(
        cls,
        *,
        model_id: str = "",
        model_name: str = "",
    ) -> CalibrationProfile:
        return cls(
            model_id=model_id,
            model_name=model_name,
            parameters={
                calibration.semantic_param: calibration
                for calibration in default_vtube_studio_calibrations()
            },
        )

    def ensure_defaults(self) -> bool:
        """Synchronize the profile with built-in default semantic mappings."""

        changed = False
        defaults = {
            calibration.semantic_param: calibration
            for calibration in default_vtube_studio_calibrations()
        }

        for semantic_param in tuple(self.parameters):
            if semantic_param in defaults:
                continue
            del self.parameters[semantic_param]
            changed = True

        for semantic_param, calibration in defaults.items():
            existing = self.parameters.get(semantic_param)
            if existing is not None:
                if _needs_default_refresh(existing, calibration):
                    self.parameters[semantic_param] = calibration
                    changed = True
                continue
            self.parameters[semantic_param] = calibration
            changed = True
        return changed

    def supports(self, semantic_param: str) -> bool:
        calibration = self.parameters.get(semantic_param)
        return calibration is not None and calibration.enabled

    def support_score(self, unit: ExpressionUnit) -> float:
        if not unit.targets:
            return 1.0
        total_weight = sum(max(0.0, target.weight) for target in unit.targets)
        if total_weight <= 0:
            return 0.0

        score = 0.0
        for target in unit.targets:
            calibration = self.parameters.get(target.semantic_param)
            if calibration is None or not calibration.enabled:
                continue
            score += max(0.0, target.weight) * calibration.confidence
        return max(0.0, min(1.0, score / total_weight))

    def resolve(
        self,
        semantic_param: str,
        value: float,
        *,
        mode: Literal["set", "add"] = "set",
        keep_alive: bool = True,
    ) -> list[ResolvedExpressionParameter]:
        calibration = self.parameters.get(semantic_param)
        if calibration is None or not calibration.enabled:
            return []

        resolved = _resolve_calibrated_value(calibration, value)
        return [
            ResolvedExpressionParameter(
                name=vts_param,
                value=resolved,
                start_value=calibration.neutral,
                mode=mode,
                keep_alive=keep_alive,
            )
            for vts_param in calibration.vts_params
        ]

    def resolve_unit(
        self,
        unit: ExpressionUnit,
    ) -> list[ControlledParameterState]:
        states: list[ControlledParameterState] = []
        for target in unit.targets:
            states.extend(
                ControlledParameterState(
                    name=resolved.name,
                    value=resolved.value,
                    mode=resolved.mode,
                    keep_alive=resolved.keep_alive,
                )
                for resolved in self.resolve(target.semantic_param, target.value)
            )
        return states


def _resolve_calibrated_value(
    calibration: SemanticParameterCalibration,
    value: float,
) -> float:
    normalized = max(-1.0, min(1.0, -value if calibration.inverted else value))
    curved = _apply_curve(abs(normalized), calibration.curve)
    if normalized >= 0:
        return calibration.neutral + curved * (
            calibration.positive_limit - calibration.neutral
        )
    return calibration.neutral - curved * (
        calibration.neutral - calibration.negative_limit
    )


def _apply_curve(value: float, curve: CalibrationCurve) -> float:
    if curve == "linear":
        return value
    if curve == "ease_in":
        return value * value
    if curve == "ease_out":
        return 1.0 - (1.0 - value) * (1.0 - value)
    if curve == "ease_in_out":
        if value < 0.5:
            return 2.0 * value * value
        return 1.0 - pow(-2.0 * value + 2.0, 2) / 2.0
    return value


def _needs_default_refresh(
    existing: SemanticParameterCalibration,
    default: SemanticParameterCalibration,
) -> bool:
    if existing.semantic_param != default.semantic_param:
        return True
    if not _limits_fit_default_vts_ranges(existing):
        return True
    if (
        existing.semantic_param == SemanticParameter.MOUTH_FROWN.value
        and existing.positive_limit > existing.neutral
    ):
        return True
    return bool(
        existing.semantic_param == SemanticParameter.HEAD_ROLL.value
        and existing.negative_limit == -30.0
        and existing.positive_limit == 30.0,
    )


def _limits_fit_default_vts_ranges(
    calibration: SemanticParameterCalibration,
) -> bool:
    for vts_param in calibration.vts_params:
        parameter_range = VTS_DEFAULT_TRACKING_PARAMETER_RANGES.get(vts_param)
        if parameter_range is None:
            return False
        values = (
            calibration.negative_limit,
            calibration.neutral,
            calibration.positive_limit,
        )
        if any(
            value < parameter_range.minimum or value > parameter_range.maximum
            for value in values
        ):
            return False
    return True


def default_vtube_studio_calibrations() -> tuple[SemanticParameterCalibration, ...]:
    """Return default semantic mappings for common VTube Studio models."""

    return (
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.BROW_INNER_UP.value,
            vts_params=["BrowLeftY", "BrowRightY"],
            neutral=0.0,
            negative_limit=0.0,
            positive_limit=1.0,
            confidence=0.35,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.BROW_OUTER_UP.value,
            vts_params=["BrowLeftY", "BrowRightY"],
            neutral=0.0,
            negative_limit=0.0,
            positive_limit=1.0,
            confidence=0.35,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.BROW_DOWN.value,
            vts_params=["BrowLeftY", "BrowRightY"],
            neutral=0.0,
            negative_limit=0.0,
            positive_limit=1.0,
            confidence=0.35,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.EYE_OPEN.value,
            vts_params=["EyeOpenLeft", "EyeOpenRight"],
            neutral=0.75,
            negative_limit=0.0,
            positive_limit=1.0,
            confidence=0.45,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.EYE_SQUINT.value,
            vts_params=["EyeOpenLeft", "EyeOpenRight"],
            neutral=0.75,
            negative_limit=0.2,
            confidence=0.45,
            inverted=True,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.EYE_WIDE.value,
            vts_params=["EyeOpenLeft", "EyeOpenRight"],
            neutral=0.75,
            negative_limit=0.0,
            positive_limit=1.0,
            confidence=0.45,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.MOUTH_OPEN.value,
            vts_params=["MouthOpen"],
            neutral=0.0,
            negative_limit=0.0,
            positive_limit=1.0,
            confidence=0.75,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.MOUTH_SMILE.value,
            vts_params=["MouthSmile"],
            neutral=0.0,
            negative_limit=0.0,
            positive_limit=1.0,
            confidence=0.75,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.MOUTH_FROWN.value,
            vts_params=["MouthSmile"],
            neutral=0.0,
            negative_limit=0.0,
            positive_limit=0.0,
            confidence=0.45,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.HEAD_YAW.value,
            vts_params=["FaceAngleX"],
            neutral=0.0,
            negative_limit=-30.0,
            positive_limit=30.0,
            confidence=0.8,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.HEAD_PITCH.value,
            vts_params=["FaceAngleY"],
            neutral=0.0,
            negative_limit=-30.0,
            positive_limit=30.0,
            confidence=0.8,
        ),
        SemanticParameterCalibration(
            semantic_param=SemanticParameter.HEAD_ROLL.value,
            vts_params=["FaceAngleZ"],
            neutral=0.0,
            negative_limit=-90.0,
            positive_limit=90.0,
            confidence=0.8,
        ),
    )

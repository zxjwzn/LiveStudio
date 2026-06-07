"""把通用动作的平滑变化换成平台能用的参数变化"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from livestudio.tween import (
    ControlledParameterState,
    ParameterTweenEngine,
    TweenRequest,
)

from .models import (
    DEFAULT_SEMANTIC_ACTION_SPECS,
    SemanticActionTarget,
    SemanticTweenRequest,
    clamp_semantic_value,
)

CurveKind: TypeAlias = Literal["linear", "ease_in", "ease_out", "ease_in_out"]


@dataclass(frozen=True, slots=True)
class ResolvedPlatformParameter:
    """这里表示已经换好的平台参数目标"""

    name: str
    value: float
    start_value: float | None
    weight: float = 1.0
    mode: Literal["set", "add"] = "set"
    keep_alive: bool = True


@dataclass(frozen=True, slots=True)
class SemanticActionState:
    """这里表示从平台参数换回来的通用动作数值"""

    action: str
    value: float
    platform_values: dict[str, float]
    weight: float = 1.0


class PlatformParameterSpec(BaseModel):
    """这里记录平台参数能用的数值范围"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    minimum: float
    maximum: float
    neutral: float
    default: float

    @model_validator(mode="after")
    def validate_range(self) -> PlatformParameterSpec:
        if self.maximum < self.minimum:
            raise ValueError("maximum cannot be less than minimum")
        if not self.minimum <= self.neutral <= self.maximum:
            raise ValueError("neutral must be within min/max range")
        if not self.minimum <= self.default <= self.maximum:
            raise ValueError("default must be within min/max range")
        return self


class SemanticActionBinding(BaseModel):
    """这里说明一个通用动作对应哪些平台参数"""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    platform_params: list[str] = Field(min_length=1)
    curve: CurveKind = "linear"


class SemanticActionProfile(BaseModel):
    """这里放通用动作到平台参数的对应关系"""

    model_config = ConfigDict(extra="forbid")

    model_id: str = ""
    model_name: str = ""
    bindings: dict[str, SemanticActionBinding] = Field(
        default_factory=dict,
        description="通用动作名字到平台参数的对应关系",
    )

    @model_validator(mode="after")
    def validate_bindings(self) -> SemanticActionProfile:
        for action, binding in self.bindings.items():
            if binding.action != action:
                raise ValueError("binding action must match its profile key")
            if action not in DEFAULT_SEMANTIC_ACTION_SPECS:
                raise ValueError(f"unknown semantic action: {action}")
        return self

    def ensure_defaults(
        self,
        *,
        bindings: Iterable[SemanticActionBinding],
    ) -> bool:
        """把这份配置和平台默认设置对齐"""

        changed = False
        default_bindings = {binding.action: binding for binding in bindings}

        for action, binding in default_bindings.items():
            existing = self.bindings.get(action)
            if existing is not None:
                continue
            self.bindings[action] = binding
            changed = True

        return changed

    def supports(self, action: str) -> bool:
        return action in self.bindings

    def support_score(self, targets: Iterable[SemanticActionTarget]) -> float:
        target_tuple = tuple(targets)
        if not target_tuple:
            return 1.0
        total_weight = sum(max(0.0, target.weight) for target in target_tuple)
        if total_weight <= 0.0:
            return 0.0

        score = 0.0
        for target in target_tuple:
            if not self.supports(target.action):
                continue
            score += max(0.0, target.weight)
        return max(0.0, min(1.0, score / total_weight))


class SemanticActionAdapter:
    """把通用动作换成平台真正要执行的平滑变化"""

    def __init__(
        self,
        profile: SemanticActionProfile,
        *,
        parameter_specs: Iterable[PlatformParameterSpec]
        | dict[str, PlatformParameterSpec],
    ) -> None:
        self.profile = profile
        self.parameter_specs = _normalize_parameter_specs(parameter_specs)
        self._validate_profile()

    def support_score(self, targets: Iterable[SemanticActionTarget]) -> float:
        return self.profile.support_score(targets)

    def platform_parameters_for(self, action: str) -> tuple[str, ...]:
        binding = self.profile.bindings.get(action)
        if binding is None:
            return ()
        return tuple(
            parameter_name
            for parameter_name in binding.platform_params
            if parameter_name in self.parameter_specs
        )

    def resolve(
        self,
        target: SemanticActionTarget,
        *,
        mode: Literal["set", "add"] = "set",
        keep_alive: bool = True,
    ) -> list[ResolvedPlatformParameter]:
        action_value = clamp_semantic_value(target.action, target.value)
        binding = self.profile.bindings.get(target.action)
        if binding is None:
            return []

        resolved: list[ResolvedPlatformParameter] = []
        for parameter_name in binding.platform_params:
            spec = self.parameter_specs.get(parameter_name)
            if spec is None:
                continue
            start_value = spec.neutral
            if target.start_value is not None:
                start_value = _resolve_bound_value(
                    binding,
                    clamp_semantic_value(target.action, target.start_value),
                    spec,
                )
            value = _resolve_bound_value(binding, action_value, spec)
            resolved.append(
                ResolvedPlatformParameter(
                    name=parameter_name,
                    value=_clamp(value, spec.minimum, spec.maximum),
                    start_value=_clamp(start_value, spec.minimum, spec.maximum),
                    weight=max(0.0, target.weight),
                    mode=mode,
                    keep_alive=keep_alive,
                ),
            )
        return resolved

    def normalize_platform_values(
        self,
        action: str,
        platform_values: dict[str, float],
    ) -> SemanticActionState | None:
        binding = self.profile.bindings.get(action)
        if binding is None:
            return None

        weighted_value = 0.0
        total_weight = 0.0
        used_values: dict[str, float] = {}
        for parameter_name in binding.platform_params:
            spec = self.parameter_specs.get(parameter_name)
            if spec is None or parameter_name not in platform_values:
                continue
            used_values[parameter_name] = platform_values[parameter_name]
            weighted_value += _normalize_bound_value(
                binding,
                platform_values[parameter_name],
                spec,
            )
            total_weight += 1.0

        if total_weight <= 0.0:
            return None
        return SemanticActionState(
            action=action,
            value=clamp_semantic_value(action, weighted_value / total_weight),
            platform_values=used_values,
            weight=total_weight,
        )

    def resolve_request(
        self,
        request: SemanticTweenRequest,
        *,
        current_states: dict[str, ControlledParameterState],
    ) -> list[TweenRequest]:
        merged = self._merge_resolved_parameters(
            resolved
            for target in request.targets
            for resolved in self.resolve(
                target,
                mode=request.mode,
                keep_alive=request.keep_alive,
            )
        )
        return [
            TweenRequest(
                parameter_name=resolved.name,
                end_value=resolved.value,
                start_value=self._resolve_start_value(resolved, current_states),
                duration=max(0.0, request.duration),
                delay=request.delay,
                easing=request.easing,
                mode=resolved.mode,
                fps=request.fps,
                priority=request.priority,
                keep_alive=resolved.keep_alive,
            )
            for resolved in merged
        ]

    async def tween(
        self,
        tween: ParameterTweenEngine,
        request: SemanticTweenRequest,
    ) -> None:
        requests = self.resolve_request(
            request,
            current_states=tween.controlled_params,
        )
        if not requests:
            return
        await asyncio.gather(
            *(tween.tween(tween_request) for tween_request in requests),
        )

    def _merge_resolved_parameters(
        self,
        resolved_parameters: Iterable[ResolvedPlatformParameter],
    ) -> list[ResolvedPlatformParameter]:
        merged: dict[str, tuple[ResolvedPlatformParameter, float, float]] = {}
        order: list[str] = []
        for resolved in resolved_parameters:
            if resolved.name not in merged:
                order.append(resolved.name)
                merged[resolved.name] = (resolved, 0.0, 0.0)
            first, weighted_value, total_weight = merged[resolved.name]
            weight = max(0.0, resolved.weight)
            merged[resolved.name] = (
                first,
                weighted_value + resolved.value * weight,
                total_weight + weight,
            )

        results: list[ResolvedPlatformParameter] = []
        for name in order:
            first, weighted_value, total_weight = merged[name]
            if total_weight <= 0.0:
                continue
            results.append(
                ResolvedPlatformParameter(
                    name=first.name,
                    value=weighted_value / total_weight,
                    start_value=first.start_value,
                    weight=1.0,
                    mode=first.mode,
                    keep_alive=first.keep_alive,
                ),
            )
        return results

    def _resolve_start_value(
        self,
        resolved: ResolvedPlatformParameter,
        current_states: dict[str, ControlledParameterState],
    ) -> float:
        current_state = current_states.get(resolved.name)
        if current_state is not None:
            return current_state.value
        if resolved.start_value is not None:
            return resolved.start_value
        spec = self.parameter_specs.get(resolved.name)
        if spec is None:
            raise KeyError(f"unknown platform parameter: {resolved.name}")
        return spec.neutral

    def _validate_profile(self) -> None:
        for action, binding in self.profile.bindings.items():
            if not _binding_references_known_parameters(binding, self.parameter_specs):
                raise ValueError(f"binding {action} references unknown platform params")


def _resolve_bound_value(
    binding: SemanticActionBinding,
    value: float,
    spec: PlatformParameterSpec,
) -> float:
    semantic_spec = DEFAULT_SEMANTIC_ACTION_SPECS.get(binding.action)
    if semantic_spec is None:
        normalized = max(-1.0, min(1.0, value))
        curved = _apply_curve(abs(normalized), binding.curve)
        if normalized >= 0:
            return spec.neutral + curved * (spec.maximum - spec.neutral)
        return spec.neutral - curved * (spec.neutral - spec.minimum)

    semantic_value = max(semantic_spec.minimum, min(semantic_spec.maximum, value))
    if semantic_value >= semantic_spec.neutral:
        span = semantic_spec.maximum - semantic_spec.neutral
        ratio = 0.0 if span <= 0.0 else (semantic_value - semantic_spec.neutral) / span
        return spec.neutral + _apply_curve(ratio, binding.curve) * (
            spec.maximum - spec.neutral
        )

    span = semantic_spec.neutral - semantic_spec.minimum
    ratio = 0.0 if span <= 0.0 else (semantic_spec.neutral - semantic_value) / span
    return spec.neutral - _apply_curve(ratio, binding.curve) * (
        spec.neutral - spec.minimum
    )


def _normalize_bound_value(
    binding: SemanticActionBinding,
    value: float,
    spec: PlatformParameterSpec,
) -> float:
    platform_value = _clamp(value, spec.minimum, spec.maximum)
    semantic_spec = DEFAULT_SEMANTIC_ACTION_SPECS.get(binding.action)
    if semantic_spec is None:
        if platform_value >= spec.neutral:
            span = spec.maximum - spec.neutral
            ratio = 0.0 if span <= 0.0 else (platform_value - spec.neutral) / span
            return _unapply_curve(ratio, binding.curve)
        span = spec.neutral - spec.minimum
        ratio = 0.0 if span <= 0.0 else (spec.neutral - platform_value) / span
        return -_unapply_curve(ratio, binding.curve)

    if platform_value >= spec.neutral:
        span = spec.maximum - spec.neutral
        ratio = 0.0 if span <= 0.0 else (platform_value - spec.neutral) / span
        return semantic_spec.neutral + _unapply_curve(ratio, binding.curve) * (
            semantic_spec.maximum - semantic_spec.neutral
        )

    span = spec.neutral - spec.minimum
    ratio = 0.0 if span <= 0.0 else (spec.neutral - platform_value) / span
    return semantic_spec.neutral - _unapply_curve(ratio, binding.curve) * (
        semantic_spec.neutral - semantic_spec.minimum
    )


def _apply_curve(value: float, curve: CurveKind) -> float:
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


def _unapply_curve(value: float, curve: CurveKind) -> float:
    value = max(0.0, min(1.0, value))
    if curve == "linear":
        return value
    if curve == "ease_in":
        return math.sqrt(value)
    if curve == "ease_out":
        return 1.0 - math.sqrt(1.0 - value)
    if curve == "ease_in_out":
        if value < 0.5:
            return math.sqrt(value / 2.0)
        return 1.0 - math.sqrt((1.0 - value) / 2.0)
    return value


def _normalize_parameter_specs(
    parameter_specs: Iterable[PlatformParameterSpec] | dict[str, PlatformParameterSpec],
) -> dict[str, PlatformParameterSpec]:
    if isinstance(parameter_specs, dict):
        normalized: dict[str, PlatformParameterSpec] = {}
        for name, spec in parameter_specs.items():
            if not isinstance(name, str):
                raise TypeError("parameter spec mapping keys must be strings")
            if not isinstance(spec, PlatformParameterSpec):
                raise TypeError("parameter spec mapping values must be specs")
            normalized[name] = spec
        return normalized
    return {spec.name: spec for spec in parameter_specs}


def _binding_references_known_parameters(
    binding: SemanticActionBinding,
    parameter_specs: dict[str, PlatformParameterSpec],
) -> bool:
    return all(
        parameter_name in parameter_specs for parameter_name in binding.platform_params
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))

"""Resolve semantic action tweens into platform parameter tweens."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from livestudio.tween import (
    ControlledParameterState,
    ParameterTweenEngine,
    TweenRequest,
)

from .models import SemanticActionTarget, SemanticTweenRequest, clamp_semantic_value

CurveKind: TypeAlias = Literal["linear", "ease_in", "ease_out", "ease_in_out"]


@dataclass(frozen=True, slots=True)
class ResolvedPlatformParameter:
    """A resolved platform parameter target."""

    name: str
    value: float
    start_value: float | None
    weight: float = 1.0
    mode: Literal["set", "add"] = "set"
    keep_alive: bool = True


class PlatformParameterSpec(BaseModel):
    """Range metadata for a concrete platform parameter."""

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
    """Mapping from one semantic action to one or more platform parameters."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1)
    platform_params: list[str] = Field(min_length=1)
    inverted: bool = False
    curve: CurveKind = "linear"
    enabled: bool = True


class SemanticActionProfile(BaseModel):
    """Platform mapping profile for semantic actions."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = ""
    model_name: str = ""
    bindings: dict[str, SemanticActionBinding] = Field(
        default_factory=dict,
        description="Semantic action id to platform parameter binding.",
    )

    @model_validator(mode="after")
    def validate_bindings(self) -> SemanticActionProfile:
        for action, binding in self.bindings.items():
            if binding.action != action:
                raise ValueError("binding action must match its profile key")
        return self

    def ensure_defaults(
        self,
        *,
        bindings: Iterable[SemanticActionBinding],
        replace_bindings: Iterable[str] = (),
    ) -> bool:
        """Synchronize this profile with platform default specs and bindings."""

        changed = False
        default_bindings = {binding.action: binding for binding in bindings}
        replacements = set(replace_bindings)

        for action, binding in default_bindings.items():
            existing = self.bindings.get(action)
            if existing is not None and action not in replacements:
                continue
            if existing == binding:
                continue
            self.bindings[action] = binding
            changed = True

        return changed

    def supports(self, action: str) -> bool:
        binding = self.bindings.get(action)
        return binding is not None and binding.enabled

    def support_score(self, targets: Iterable[SemanticActionTarget] | object) -> float:
        target_values = getattr(targets, "targets", targets)
        target_tuple = tuple(target_values)
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
    """Resolve normalized semantic actions into concrete platform tweens."""

    def __init__(
        self,
        profile: SemanticActionProfile,
        *,
        parameter_specs: Iterable[PlatformParameterSpec]
        | Mapping[str, PlatformParameterSpec],
    ) -> None:
        self.profile = profile
        self.parameter_specs = _normalize_parameter_specs(parameter_specs)
        self._validate_profile()

    def support_score(self, targets: Iterable[SemanticActionTarget] | object) -> float:
        target_values = getattr(targets, "targets", targets)
        return self.profile.support_score(target_values)

    def resolve(
        self,
        target: SemanticActionTarget,
        *,
        mode: Literal["set", "add"] = "set",
        keep_alive: bool = True,
    ) -> list[ResolvedPlatformParameter]:
        action_value = clamp_semantic_value(target.action, target.value)
        binding = self.profile.bindings.get(target.action)
        if binding is None or not binding.enabled:
            return []

        resolved: list[ResolvedPlatformParameter] = []
        for parameter_name in binding.platform_params:
            spec = self.parameter_specs.get(parameter_name)
            if spec is None:
                continue
            start_value = (
                None
                if target.start_value is None
                else _resolve_bound_value(
                    binding,
                    clamp_semantic_value(target.action, target.start_value),
                    spec,
                )
            )
            value = _resolve_bound_value(binding, action_value, spec)
            resolved.append(
                ResolvedPlatformParameter(
                    name=parameter_name,
                    value=_clamp(value, spec.minimum, spec.maximum),
                    start_value=(
                        spec.neutral
                        if target.start_value is None
                        else _clamp(start_value, spec.minimum, spec.maximum)
                    ),
                    weight=max(0.0, target.weight),
                    mode=mode,
                    keep_alive=keep_alive,
                ),
            )
        return resolved

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
        return resolved.start_value

    def _validate_profile(self) -> None:
        for action, binding in self.profile.bindings.items():
            if not _binding_references_known_parameters(binding, self.parameter_specs):
                raise ValueError(f"binding {action} references unknown platform params")


def _resolve_bound_value(
    binding: SemanticActionBinding,
    value: float,
    spec: PlatformParameterSpec,
) -> float:
    normalized = max(-1.0, min(1.0, -value if binding.inverted else value))
    curved = _apply_curve(abs(normalized), binding.curve)
    if normalized >= 0:
        return spec.neutral + curved * (spec.maximum - spec.neutral)
    return spec.neutral - curved * (spec.neutral - spec.minimum)


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


def _normalize_parameter_specs(
    parameter_specs: Iterable[PlatformParameterSpec]
    | Mapping[str, PlatformParameterSpec],
) -> dict[str, PlatformParameterSpec]:
    if isinstance(parameter_specs, Mapping):
        return dict(parameter_specs)
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

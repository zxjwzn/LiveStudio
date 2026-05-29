"""High-level expression synthesis service."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from livestudio.tween import (
    ControlledParameterState,
    ParameterTweenEngine,
    TweenRequest,
)

from .calibration import CalibrationProfile
from .models import EmotionRequest, ExpressionUnit, SelectedExpression, UnitTarget
from .selector import ExpressionSelector


class ExpressionService:
    """Selects and applies calibrated expression units."""

    def __init__(
        self,
        *,
        tween: ParameterTweenEngine,
        calibration: CalibrationProfile,
        selector: ExpressionSelector,
    ) -> None:
        self.tween = tween
        self.calibration = calibration
        self.selector = selector

    async def express(self, request: EmotionRequest) -> SelectedExpression:
        selected = self.selector.select(request)
        await self.apply_targets(
            selected.targets,
            duration_scale=request.duration_scale,
            priority=max(unit.priority for unit in selected.units.values()),
            easing=self._dominant_easing(selected),
        )
        return selected

    def preview(self, request: EmotionRequest) -> SelectedExpression:
        return self.selector.preview(request)

    async def apply_units(
        self,
        units: Iterable[ExpressionUnit],
        *,
        duration_scale: float = 1.0,
    ) -> None:
        unit_tuple = tuple(units)
        targets = tuple(target for unit in unit_tuple for target in unit.targets)
        priority = max((unit.priority for unit in unit_tuple), default=40)
        easing = unit_tuple[0].easing if unit_tuple else "in_out_sine"
        await self.apply_targets(
            targets,
            duration_scale=duration_scale,
            priority=priority,
            easing=easing,
        )

    async def apply_targets(
        self,
        targets: Iterable[UnitTarget],
        *,
        duration_scale: float = 1.0,
        priority: int = 40,
        easing: str = "in_out_sine",
    ) -> None:
        requests: list[TweenRequest] = []
        current_states = self.tween.controlled_params
        for target in targets:
            for state in self.calibration.resolve(target.semantic_param, target.value):
                requests.append(
                    TweenRequest(
                        parameter_name=state.name,
                        end_value=state.value,
                        start_value=self._resolve_start_value(
                            state.name,
                            state.start_value,
                            current_states,
                        ),
                        duration=max(0.0, 0.35 * duration_scale),
                        easing=easing,
                        mode=state.mode,
                        priority=priority,
                        keep_alive=state.keep_alive,
                    ),
                )

        if not requests:
            return
        await asyncio.gather(*(self.tween.tween(request) for request in requests))

    def _dominant_easing(self, selected: SelectedExpression) -> str:
        for unit in selected.units.values():
            if unit.targets:
                return unit.easing
        return "in_out_sine"

    def _resolve_start_value(
        self,
        parameter_name: str,
        fallback_start_value: float,
        current_states: dict[str, ControlledParameterState],
    ) -> float:
        current_state = current_states.get(parameter_name)
        if current_state is not None:
            return current_state.value
        return fallback_start_value

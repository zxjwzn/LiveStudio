"""High-level expression synthesis service."""

from __future__ import annotations

from collections.abc import Iterable

from livestudio.services.platforms import PlatformService
from livestudio.services.semantic_actions import (
    SemanticActionTarget,
    SemanticTweenRequest,
)

from .models import EmotionRequest, ExpressionUnit, SelectedExpression
from .selector import ExpressionSelector


class ExpressionService:
    """Selects and applies calibrated expression units."""

    def __init__(
        self,
        *,
        platform: PlatformService,
        selector: ExpressionSelector,
    ) -> None:
        self.platform = platform
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
        targets: Iterable[SemanticActionTarget],
        *,
        duration_scale: float = 1.0,
        priority: int = 40,
        easing: str = "in_out_sine",
    ) -> None:
        await self.platform.tween_semantic(
            SemanticTweenRequest(
                targets=tuple(targets),
                duration=0.35 * duration_scale,
                easing=easing,
                priority=priority,
                keep_alive=True,
            ),
        )

    def _dominant_easing(self, selected: SelectedExpression) -> str:
        for unit in selected.units.values():
            if unit.targets:
                return unit.easing
        return "in_out_sine"

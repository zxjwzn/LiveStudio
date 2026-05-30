"""Emotion-driven expression unit selector."""

from __future__ import annotations

import itertools
import math
import random
from collections import deque
from collections.abc import Iterable

from .calibration import CalibrationProfile
from .models import (
    EmotionKind,
    EmotionRequest,
    ExpressionRegion,
    ExpressionUnit,
    ScoredExpressionUnit,
    SelectedExpression,
    UnitTarget,
)

REGION_ORDER: tuple[ExpressionRegion, ...] = (
    ExpressionRegion.BROW,
    ExpressionRegion.EYE,
    ExpressionRegion.MOUTH,
    ExpressionRegion.HEAD,
)


class ExpressionSelector:
    """Selects compatible expression units for an emotion request."""

    def __init__(
        self,
        units: Iterable[ExpressionUnit],
        calibration: CalibrationProfile,
        *,
        rng: random.Random | None = None,
        top_per_region: int = 5,
        recent_size: int = 16,
    ) -> None:
        self.units = tuple(units)
        self.calibration = calibration
        self.rng = rng or random.Random()
        self.top_per_region = top_per_region
        self._recent_unit_ids: deque[str] = deque(maxlen=recent_size)

    def select(self, request: EmotionRequest) -> SelectedExpression:
        regional_candidates = [
            self._rank_region(region, request) for region in REGION_ORDER
        ]
        combos = [
            tuple(scored_units)
            for scored_units in itertools.product(*regional_candidates)
        ]
        if not combos:
            raise ValueError("no expression units are available for selection")

        scored_combos = [(self._score_combo(combo, request), combo) for combo in combos]
        scored_combos.sort(key=lambda item: item[0], reverse=True)
        selected_score, selected_combo = self._sample_combo(scored_combos, request)
        units = {scored.unit.region: scored.unit for scored in selected_combo}
        for unit in units.values():
            self._recent_unit_ids.append(unit.id)

        targets = self._merge_targets(unit for unit in units.values())
        emotion_match = sum(scored.emotion_match for scored in selected_combo) / len(
            selected_combo,
        )
        return SelectedExpression(
            units=units,
            score=selected_score,
            emotion_match=emotion_match,
            targets=targets,
        )

    def preview(self, request: EmotionRequest) -> SelectedExpression:
        state = tuple(self._recent_unit_ids)
        try:
            return self.select(request)
        finally:
            self._recent_unit_ids.clear()
            self._recent_unit_ids.extend(state)

    def _rank_region(
        self,
        region: ExpressionRegion,
        request: EmotionRequest,
    ) -> list[ScoredExpressionUnit]:
        candidates = [
            self._score_unit(unit, request)
            for unit in self.units
            if unit.region is region
        ]
        candidates = self._filter_emotion_candidates(candidates, request)
        if not request.allow_none_regions:
            candidates = [
                candidate for candidate in candidates if candidate.unit.targets
            ]
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates[: self.top_per_region]

    def _filter_emotion_candidates(
        self,
        candidates: list[ScoredExpressionUnit],
        request: EmotionRequest,
    ) -> list[ScoredExpressionUnit]:
        expressive_weight = self._expressive_weight(request)
        if expressive_weight <= 0.0:
            return candidates

        matching_targets = [
            candidate
            for candidate in candidates
            if candidate.unit.targets and candidate.emotion_match > 0.0
        ]
        if not matching_targets:
            return candidates
        return matching_targets

    def _score_unit(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest,
    ) -> ScoredExpressionUnit:
        emotion_match = sum(
            request_weight * unit.emotions.get(emotion, 0.0)
            for emotion, request_weight in request.emotions.items()
        )
        intensity_match = 1.0 - abs(request.intensity - unit.intensity)
        calibration_support = self.calibration.support_score(unit)
        novelty = 0.2 if unit.id in self._recent_unit_ids else 1.0
        none_penalty = self._none_region_penalty(unit, request)

        score = (
            emotion_match * 0.45
            + intensity_match * 0.15
            + calibration_support * 0.20
            + unit.naturalness * 0.10
            + unit.base_weight * 0.05
            + novelty * 0.05
            - none_penalty
        )
        return ScoredExpressionUnit(
            unit=unit,
            score=max(0.0, score),
            emotion_match=emotion_match,
            calibration_support=calibration_support,
        )

    def _none_region_penalty(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest,
    ) -> float:
        if unit.targets:
            return 0.0
        expressive_weight = self._expressive_weight(request)
        if expressive_weight <= 0.0:
            return 0.0
        return min(0.35, expressive_weight * request.intensity * 0.35)

    def _expressive_weight(self, request: EmotionRequest) -> float:
        return sum(
            weight
            for emotion, weight in request.emotions.items()
            if emotion is not EmotionKind.NEUTRAL
        )

    def _score_combo(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
    ) -> float:
        score = sum(scored.score for scored in combo)
        unit_ids = {scored.unit.id for scored in combo}
        tags = set().union(*(scored.unit.tags for scored in combo))

        for scored in combo:
            unit = scored.unit
            score += sum(
                bonus
                for target_id, bonus in unit.synergies.items()
                if target_id in unit_ids or target_id in tags
            )
            if unit.conflicts.intersection(unit_ids) or unit.conflicts.intersection(
                tags,
            ):
                score -= 0.75

        target_params: dict[str, int] = {}
        total_intensity = 0.0
        for scored in combo:
            total_intensity += scored.unit.intensity
            for target in scored.unit.targets:
                target_params[target.semantic_param] = (
                    target_params.get(target.semantic_param, 0) + 1
                )

        collisions = sum(count - 1 for count in target_params.values() if count > 1)
        score -= collisions * 0.35

        expected_intensity = request.intensity * len(REGION_ORDER)
        score -= max(0.0, total_intensity - expected_intensity - 0.8) * 0.25
        return score

    def _sample_combo(
        self,
        scored_combos: list[tuple[float, tuple[ScoredExpressionUnit, ...]]],
        request: EmotionRequest,
    ) -> tuple[float, tuple[ScoredExpressionUnit, ...]]:
        if request.randomness <= 0.0:
            return scored_combos[0]

        top_count = min(8, len(scored_combos))
        top = scored_combos[:top_count]
        temperature = max(0.05, request.randomness)
        best_score = top[0][0]
        weights = [math.exp((score - best_score) / temperature) for score, _ in top]
        return self.rng.choices(top, weights=weights, k=1)[0]

    def _merge_targets(
        self,
        units: Iterable[ExpressionUnit],
    ) -> tuple[UnitTarget, ...]:
        merged: dict[str, tuple[float, float]] = {}
        order: list[str] = []
        for unit in units:
            for target in unit.targets:
                if target.semantic_param not in merged:
                    order.append(target.semantic_param)
                    merged[target.semantic_param] = (0.0, 0.0)
                weighted_value, total_weight = merged[target.semantic_param]
                weight = max(0.0, target.weight)
                merged[target.semantic_param] = (
                    weighted_value + target.value * weight,
                    total_weight + weight,
                )

        targets: list[UnitTarget] = []
        for semantic_param in order:
            weighted_value, total_weight = merged[semantic_param]
            if total_weight <= 0:
                continue
            targets.append(
                UnitTarget(
                    semantic_param=semantic_param,
                    value=weighted_value / total_weight,
                ),
            )
        return tuple(targets)

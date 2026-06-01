"""Emotion-driven expression unit selector."""

from __future__ import annotations

import itertools
import math
import random
from collections import deque
from collections.abc import Iterable

from livestudio.services.semantic_actions import (
    SemanticActionProfile,
    SemanticActionTarget,
    clamp_semantic_value,
)

from .models import (
    EmotionKind,
    EmotionRequest,
    ExpressionCombinationRule,
    ExpressionRegion,
    ExpressionSignature,
    ExpressionUnit,
    ScoredExpressionUnit,
    SelectedExpression,
)
from .rules import BUILTIN_COMBINATION_RULES

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
        semantic_profile: SemanticActionProfile,
        *,
        rng: random.Random | None = None,
        top_per_region: int = 5,
        recent_size: int = 16,
        combination_rules: Iterable[
            ExpressionCombinationRule
        ] = BUILTIN_COMBINATION_RULES,
    ) -> None:
        self.units = tuple(units)
        self.semantic_profile = semantic_profile
        self.rng = rng or random.Random()
        self.top_per_region = top_per_region
        self._recent_unit_ids: deque[str] = deque(maxlen=recent_size)
        self._recent_expressions: deque[ExpressionSignature] = deque(maxlen=recent_size)
        self.combination_rules = tuple(combination_rules)

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

        scored_combos = [
            (score, combo)
            for combo in combos
            if math.isfinite(score := self._score_combo(combo, request))
        ]
        if not scored_combos:
            raise ValueError("no compatible expression unit combinations are available")
        scored_combos.sort(key=lambda item: item[0], reverse=True)
        selected_score, selected_combo = self._sample_combo(scored_combos, request)
        units = {scored.unit.region: scored.unit for scored in selected_combo}
        for unit in units.values():
            self._recent_unit_ids.append(unit.id)

        targets = self._merge_targets((unit for unit in units.values()), request)
        self._recent_expressions.append(
            self._build_signature(selected_combo, targets, request),
        )
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
        expression_state = tuple(self._recent_expressions)
        rng_state = self.rng.getstate()
        try:
            return self.select(request)
        finally:
            self._recent_unit_ids.clear()
            self._recent_unit_ids.extend(state)
            self._recent_expressions.clear()
            self._recent_expressions.extend(expression_state)
            self.rng.setstate(rng_state)

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
        platform_support = self.semantic_profile.support_score(unit.targets)
        novelty = 0.2 if unit.id in self._recent_unit_ids else 1.0
        none_penalty = self._none_region_penalty(unit, request)

        score = (
            emotion_match * 0.45
            + intensity_match * 0.15
            + platform_support * 0.20
            + unit.naturalness * 0.10
            + unit.base_weight * 0.05
            + novelty * 0.05
            - none_penalty
        )
        return ScoredExpressionUnit(
            unit=unit,
            score=max(0.0, score),
            emotion_match=emotion_match,
            platform_support=platform_support,
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

        rule_penalty = self._combination_rule_penalty(unit_ids, tags, request)
        if math.isinf(rule_penalty):
            return -math.inf
        score -= rule_penalty

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
                return -math.inf
            score -= sum(
                penalty
                for target_id, penalty in unit.soft_conflicts.items()
                if target_id in unit_ids or target_id in tags
            )

        target_params: dict[str, int] = {}
        total_intensity = 0.0
        for scored in combo:
            total_intensity += scored.unit.intensity
            for target in scored.unit.targets:
                target_params[target.action] = target_params.get(target.action, 0) + 1

        collisions = sum(count - 1 for count in target_params.values() if count > 1)
        score -= collisions * 0.35

        expected_intensity = request.intensity * len(REGION_ORDER)
        score -= max(0.0, total_intensity - expected_intensity - 0.8) * 0.25
        score -= self._history_penalty(combo, request)
        return score

    def _combination_rule_penalty(
        self,
        unit_ids: set[str],
        tags: set[str],
        request: EmotionRequest,
    ) -> float:
        active_emotions = {
            emotion for emotion, weight in request.emotions.items() if weight > 0.0
        }
        penalty = 0.0
        for rule in self.combination_rules:
            if rule.emotions and not rule.emotions.intersection(active_emotions):
                continue
            if rule.require_tags and not rule.require_tags.issubset(tags):
                continue
            if rule.require_unit_ids and not rule.require_unit_ids.issubset(unit_ids):
                continue
            if rule.forbid_tags and not rule.forbid_tags.intersection(tags):
                continue
            if rule.forbid_unit_ids and not rule.forbid_unit_ids.intersection(unit_ids):
                continue
            if math.isinf(rule.penalty):
                return math.inf
            penalty += max(0.0, rule.penalty)
        return penalty

    def _history_penalty(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
    ) -> float:
        if request.history_avoidance <= 0.0 or not self._recent_expressions:
            return 0.0

        unit_ids = tuple(scored.unit.id for scored in combo)
        targets = self._merge_targets((scored.unit for scored in combo), request=None)
        signature = self._build_signature(combo, targets, request)
        recent_count = len(self._recent_expressions)
        max_similarity = 0.0
        for index, recent in enumerate(self._recent_expressions):
            recency = (index + 1) / recent_count
            similarity = self._signature_similarity(signature, recent, unit_ids)
            max_similarity = max(max_similarity, similarity * recency)
        return max_similarity * request.history_avoidance

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
        request: EmotionRequest | None = None,
    ) -> tuple[SemanticActionTarget, ...]:
        merged: dict[str, tuple[float, float]] = {}
        order: list[str] = []
        jitter_by_action: dict[str, float] = {}
        for unit in units:
            for target in unit.targets:
                if target.action not in merged:
                    order.append(target.action)
                    merged[target.action] = (0.0, 0.0)
                    jitter_by_action[target.action] = 0.0
                weighted_value, total_weight = merged[target.action]
                weight = max(0.0, target.weight)
                jitter_by_action[target.action] = max(
                    jitter_by_action[target.action],
                    unit.jitter_by_action.get(target.action, unit.value_jitter),
                )
                merged[target.action] = (
                    weighted_value + target.value * weight,
                    total_weight + weight,
                )

        targets: list[SemanticActionTarget] = []
        for action in order:
            weighted_value, total_weight = merged[action]
            if total_weight <= 0:
                continue
            targets.append(
                SemanticActionTarget(
                    action=action,
                    value=self._apply_target_jitter(
                        action,
                        weighted_value / total_weight,
                        jitter_by_action[action],
                        request,
                    ),
                ),
            )
        return tuple(targets)

    def _apply_target_jitter(
        self,
        action: str,
        value: float,
        jitter: float,
        request: EmotionRequest | None,
    ) -> float:
        if request is None:
            return clamp_semantic_value(action, value)
        jitter = max(0.0, jitter) * request.randomness
        if request.value_jitter > 0.0:
            jitter = max(jitter, request.value_jitter * request.randomness)
        if jitter <= 0.0:
            return clamp_semantic_value(action, value)
        return clamp_semantic_value(action, value + self.rng.uniform(-jitter, jitter))

    def _build_signature(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        targets: tuple[SemanticActionTarget, ...],
        request: EmotionRequest,
    ) -> ExpressionSignature:
        dominant_emotion = max(request.emotions.items(), key=lambda item: item[1])[0]
        return ExpressionSignature(
            unit_ids=tuple(scored.unit.id for scored in combo),
            target_values={target.action: target.value for target in targets},
            dominant_emotion=dominant_emotion,
            intensity=request.intensity,
        )

    def _signature_similarity(
        self,
        current: ExpressionSignature,
        recent: ExpressionSignature,
        current_unit_ids: tuple[str, ...],
    ) -> float:
        current_units = set(current_unit_ids)
        recent_units = set(recent.unit_ids)
        unit_similarity = len(current_units & recent_units) / max(
            len(current_units | recent_units),
            1,
        )

        shared_actions = set(current.target_values).intersection(recent.target_values)
        if shared_actions:
            target_similarity = sum(
                max(
                    0.0,
                    1.0
                    - abs(current.target_values[action] - recent.target_values[action])
                    / 2.0,
                )
                for action in shared_actions
            ) / len(shared_actions)
        else:
            target_similarity = 0.0

        emotion_similarity = (
            1.0 if current.dominant_emotion is recent.dominant_emotion else 0.0
        )
        intensity_similarity = max(0.0, 1.0 - abs(current.intensity - recent.intensity))
        return (
            unit_similarity * 0.45
            + target_similarity * 0.30
            + emotion_similarity * 0.15
            + intensity_similarity * 0.10
        )

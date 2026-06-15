"""按情绪挑表情动作的选择器"""

from __future__ import annotations

import math
import random
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from livestudio.services.semantic_actions import (
    DEFAULT_SEMANTIC_ACTION_SPECS,
    SemanticActionProfile,
    clamp_semantic_value,
)

from .intents import (
    BUILTIN_EXPRESSION_INTENTS,
    ExpressionIntent,
    ExpressionIntentOptional,
)
from .models import (
    EmotionKind,
    EmotionRequest,
    ExpressionCombinationRule,
    ExpressionRegion,
    ExpressionSignature,
    ExpressionTarget,
    ExpressionUnit,
    ScoredExpressionUnit,
    SelectedExpression,
)
from .rules import BUILTIN_COMBINATION_RULES

_SEMANTIC_SPECS_BY_ACTION = {spec.id.value: spec for spec in DEFAULT_SEMANTIC_ACTION_SPECS}


@dataclass(frozen=True, slots=True)
class EmotionVectorState:
    composition: Mapping[EmotionKind, float]
    energy: float
    effective_intensity: float
    explicit_intent: bool


@dataclass(frozen=True, slots=True)
class OptionalUnitCandidate:
    units: tuple[ExpressionUnit, ...]
    score: float
    weight: float


class ExpressionSelector:
    """根据情绪请求挑出一个或多个能表达意图的表情动作"""

    def __init__(
        self,
        units: Iterable[ExpressionUnit],
        semantic_profile: SemanticActionProfile,
        *,
        rng: random.Random | None = None,
        top_candidates: int = 12,
        beam_width: int = 8,
        recent_size: int = 16,
        intents: Iterable[ExpressionIntent] = BUILTIN_EXPRESSION_INTENTS,
        combination_rules: Iterable[ExpressionCombinationRule] = BUILTIN_COMBINATION_RULES,
    ) -> None:
        self.units = tuple(units)
        self.units_by_id = {unit.id: unit for unit in self.units}
        self.semantic_profile = semantic_profile
        self.rng = rng or random.Random()
        self.top_candidates = top_candidates
        self.beam_width = beam_width
        self._recent_unit_ids: deque[str] = deque(maxlen=recent_size)
        self._recent_expressions: deque[ExpressionSignature] = deque(maxlen=recent_size)
        self.intents = tuple(intents)
        self.intents_by_id = {intent.id: intent for intent in self.intents}
        self.combination_rules = tuple(combination_rules)

    def select(self, request: EmotionRequest) -> SelectedExpression:
        emotion_state = self._emotion_vector_state(request)
        intent = self._resolve_intent(request, emotion_state)
        return self._select_from_intent(intent, request, emotion_state)

    def _resolve_intent(
        self,
        request: EmotionRequest,
        emotion_state: EmotionVectorState,
    ) -> ExpressionIntent:
        if request.intent is not None:
            intent = self.intents_by_id.get(request.intent)
            if intent is None:
                raise ValueError(f"unknown expression intent: {request.intent}")
            return intent

        scored = [(self._score_intent(intent, request, emotion_state), intent) for intent in self.intents]
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored or scored[0][0] < 0.5:
            raise ValueError("no expression intent matches request")
        return scored[0][1]

    def _score_intent(
        self,
        intent: ExpressionIntent,
        request: EmotionRequest,
        emotion_state: EmotionVectorState,
    ) -> float:
        emotion_score = self._emotion_signature_match(
            intent.emotion_profile,
            emotion_state.composition,
        )
        if emotion_score <= 0.0:
            return 0.0
        energy_low, energy_high = intent.energy_range
        if energy_low <= emotion_state.energy <= energy_high:
            energy_score = 1.0
        else:
            energy_distance = min(
                abs(emotion_state.energy - energy_low),
                abs(emotion_state.energy - energy_high),
            )
            energy_score = max(0.0, 1.0 - energy_distance)
        intensity_low, intensity_high = intent.intensity_range
        if intensity_low <= request.intensity <= intensity_high:
            intensity_score = 1.0
        else:
            distance = min(
                abs(request.intensity - intensity_low),
                abs(request.intensity - intensity_high),
            )
            intensity_score = max(0.0, 1.0 - distance)
        available_score = self._intent_availability_score(intent)
        return (
            emotion_score * 0.62
            + energy_score * 0.14
            + intensity_score * 0.10
            + available_score * 0.08
            + intent.naturalness * 0.06
        )

    def _emotion_signature_match(
        self,
        expected: Mapping[EmotionKind, float],
        actual: Mapping[EmotionKind, float],
    ) -> float:
        all_emotions = set(expected) | set(actual)
        distance = sum(
            abs(
                max(0.0, expected.get(emotion, 0.0)) - max(0.0, actual.get(emotion, 0.0)),
            )
            for emotion in all_emotions
        )
        return max(0.0, 1.0 - distance / 2.0)

    def _emotion_vector_state(self, request: EmotionRequest) -> EmotionVectorState:
        expressive = {
            emotion: max(0.0, value)
            for emotion, value in request.emotions.items()
            if emotion is not EmotionKind.NEUTRAL and value > 0.0
        }
        if not expressive:
            expressive = {
                EmotionKind.NEUTRAL: max(
                    0.0,
                    request.emotions.get(EmotionKind.NEUTRAL, 1.0),
                ),
            }

        total = sum(expressive.values())
        composition = (
            {emotion: value / total for emotion, value in expressive.items()} if total > 0.0 else {EmotionKind.NEUTRAL: 1.0}
        )
        energy = max(expressive.values(), default=0.0)
        explicit_intent = request.intent is not None
        effective_intensity = request.intensity if explicit_intent else request.intensity * energy
        return EmotionVectorState(
            composition=composition,
            energy=energy,
            effective_intensity=effective_intensity,
            explicit_intent=explicit_intent,
        )

    def _intent_availability_score(self, intent: ExpressionIntent) -> float:
        required_units = [self.units_by_id[unit_id] for unit_id in intent.required_units if unit_id in self.units_by_id]
        if len(required_units) != len(intent.required_units):
            return 0.0
        return self.semantic_profile.support_score(
            target for unit in required_units for target in unit.targets
        )

    def _select_from_intent(
        self,
        intent: ExpressionIntent,
        request: EmotionRequest,
        emotion_state: EmotionVectorState,
    ) -> SelectedExpression:
        missing = [unit_id for unit_id in intent.required_units if unit_id not in self.units_by_id]
        if missing:
            raise ValueError(
                f"intent {intent.id} references unknown required units: {', '.join(missing)}",
            )

        required = [self.units_by_id[unit_id] for unit_id in intent.required_units]
        forbidden = set(intent.forbidden_units)
        variant_strengths = self._intent_variant_strengths(intent, emotion_state)
        optional_items = self._intent_optional_items(intent, variant_strengths)
        optional_weights = self._unit_optional_weights(optional_items)
        candidates = [
            self._score_unit_for_template(unit, optional_weights.get(unit.id, 0.0))
            for unit in self.units
            if unit.id not in forbidden and unit.id not in intent.required_units
        ]
        candidates = [
            candidate for candidate in candidates if candidate.platform_support >= 1.0 and candidate.template_weight >= 0.2
        ]
        candidates = self._choose_optional_exclusive_candidates(
            candidates,
            optional_weights,
            request,
        )
        candidates = self._filter_optional_candidates_by_randomness(
            candidates,
            request,
        )
        optional_candidates = self._build_optional_candidates(
            intent,
            optional_items,
            candidates,
            optional_weights,
            forbidden,
            request,
        )
        optional_candidates.sort(
            key=lambda candidate: (candidate.weight, candidate.score),
            reverse=True,
        )

        selected_units = list(required)
        selected_unit_ids = {unit.id for unit in selected_units}
        for candidate in optional_candidates:
            if len(selected_units) >= request.max_units:
                break
            candidate_unit_ids = {unit.id for unit in candidate.units}
            if selected_unit_ids.intersection(candidate_unit_ids):
                continue
            if len(selected_units) + len(candidate.units) > request.max_units:
                continue
            trial_units = (*selected_units, *candidate.units)
            trial_scored = tuple(
                self._score_unit_for_template(
                    unit,
                    1.0 if unit.id in intent.required_units else optional_weights.get(unit.id, 0.0),
                )
                for unit in trial_units
            )
            if math.isfinite(self._score_combo(trial_scored, request)):
                selected_units.extend(candidate.units)
                selected_unit_ids.update(candidate_unit_ids)

        scored_combo = tuple(
            self._score_unit_for_template(
                unit,
                1.0 if unit.id in intent.required_units else optional_weights.get(unit.id, 0.0),
            )
            for unit in selected_units
        )
        combo_score = self._score_combo(scored_combo, request)
        if not math.isfinite(combo_score):
            raise ValueError(f"intent {intent.id} cannot build a compatible expression")

        units = tuple(selected_units)
        target_offsets = self._intent_target_offsets(intent, variant_strengths)
        targets = self._merge_targets(
            units,
            request,
            emotion_state=emotion_state,
            target_offsets=target_offsets,
        )
        semantic_tags = frozenset({self._dominant_emotion(request).value, intent.id})

        for unit in units:
            self._recent_unit_ids.append(unit.id)
        self._recent_expressions.append(
            self._build_signature(units, targets, semantic_tags, request),
        )

        return SelectedExpression(
            units=units,
            intent_id=intent.id,
            units_by_region=self._units_by_region(units),
            score=combo_score,
            intent_match=self._score_intent(intent, request, emotion_state),
            expression_strength=emotion_state.effective_intensity,
            semantic_tags=semantic_tags,
            targets=targets,
        )

    def _intent_variant_strengths(
        self,
        intent: ExpressionIntent,
        emotion_state: EmotionVectorState,
    ) -> dict[str, float]:
        intent_composition = self._normalized_emotions(intent.emotion_profile)
        strengths: dict[str, float] = {}
        for variant in intent.variants:
            expected = max(0.0, intent_composition.get(variant.emotion, 0.0))
            actual = max(0.0, emotion_state.composition.get(variant.emotion, 0.0))
            delta = actual - expected
            if variant.direction == "below":
                delta = -delta
            strengths[variant.id] = max(
                0.0,
                min(1.0, delta * emotion_state.energy * 4.0),
            )
        return strengths

    def _normalized_emotions(
        self,
        emotions: Mapping[EmotionKind, float],
    ) -> dict[EmotionKind, float]:
        values = {emotion: max(0.0, value) for emotion, value in emotions.items() if value > 0.0}
        total = sum(values.values())
        if total <= 0.0:
            return {EmotionKind.NEUTRAL: 1.0}
        return {emotion: value / total for emotion, value in values.items()}

    def _intent_optional_items(
        self,
        intent: ExpressionIntent,
        variant_strengths: Mapping[str, float],
    ) -> tuple[ExpressionIntentOptional, ...]:
        weights = {item.id: item.weight for item in intent.optional_units}
        variants_by_id = {variant.id: variant for variant in intent.variants}
        for variant_id, strength in variant_strengths.items():
            variant = variants_by_id[variant_id]
            for item_id, adjustment in variant.optional_adjustments.items():
                weights[item_id] = max(
                    0.0,
                    weights.get(item_id, 0.0) + adjustment * strength,
                )
        return tuple(
            ExpressionIntentOptional(
                id=item.id,
                units=item.units,
                weight=weights.get(item.id, item.weight),
            )
            for item in intent.optional_units
        )

    def _unit_optional_weights(
        self,
        optional_items: tuple[ExpressionIntentOptional, ...],
    ) -> dict[str, float]:
        weights: dict[str, float] = {}
        for item in optional_items:
            for unit_id in item.units:
                weights[unit_id] = max(weights.get(unit_id, 0.0), item.weight)
        return weights

    def _intent_target_offsets(
        self,
        intent: ExpressionIntent,
        variant_strengths: Mapping[str, float],
    ) -> dict[str, float]:
        offsets: dict[str, float] = {}
        variants_by_id = {variant.id: variant for variant in intent.variants}
        for variant_id, strength in variant_strengths.items():
            variant = variants_by_id[variant_id]
            for action, offset in variant.target_offsets.items():
                offsets[action] = offsets.get(action, 0.0) + offset * strength
        return offsets

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

    def merge_unit_targets(
        self,
        units: Iterable[ExpressionUnit],
        request: EmotionRequest | None = None,
    ) -> tuple[ExpressionTarget, ...]:
        return self._merge_targets(
            units,
            request
            or EmotionRequest(
                emotions={EmotionKind.NEUTRAL: 1.0},
                intensity=1.0,
                randomness=0.0,
            ),
        )

    def _score_unit_for_template(
        self,
        unit: ExpressionUnit,
        template_weight: float,
    ) -> ScoredExpressionUnit:
        target_tuple = self._targets_for_unit(unit, None)
        platform_support = self.semantic_profile.support_score(target_tuple)
        novelty = 0.3 if unit.id in self._recent_unit_ids else 1.0
        score = (
            max(0.0, template_weight) * 0.55
            + platform_support * 0.20
            + unit.naturalness * 0.15
            + unit.base_weight * 0.05
            + novelty * 0.05
        )
        return ScoredExpressionUnit(
            unit=unit,
            score=max(0.0, score),
            template_weight=max(0.0, template_weight),
            platform_support=platform_support,
        )

    def _score_unit(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest,
    ) -> ScoredExpressionUnit:
        _ = request
        return self._score_unit_for_template(unit, unit.base_weight)

    def _score_combo(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
    ) -> float:
        if not combo:
            return -math.inf

        unit_ids = {scored.unit.id for scored in combo}
        rule_score = self._combination_rule_score(unit_ids, request)
        if rule_score == -math.inf:
            return -math.inf

        score = sum(scored.score for scored in combo)
        score += rule_score
        score += self._coverage_score(combo) * 0.18
        score -= self._history_penalty(combo, request)
        score -= max(0, len(combo) - 1) * 0.08
        return score

    def _coverage_score(self, combo: tuple[ScoredExpressionUnit, ...]) -> float:
        regions = set().union(*(scored.unit.regions for scored in combo))
        return min(1.0, len(regions) / 4.0)

    def _combination_rule_score(
        self,
        unit_ids: set[str],
        request: EmotionRequest,
    ) -> float:
        score = 0.0
        active_emotions = {emotion for emotion, weight in request.emotions.items() if weight > 0.0}
        for rule in self.combination_rules:
            if rule.emotions and not rule.emotions.intersection(active_emotions):
                continue
            if rule.required_unit_ids and not rule.required_unit_ids.issubset(unit_ids):
                continue
            if rule.excluded_unit_ids and not rule.excluded_unit_ids.intersection(
                unit_ids,
            ):
                continue
            if rule.any_of_unit_ids and len(rule.any_of_unit_ids.intersection(unit_ids)) <= 1:
                continue
            if math.isinf(rule.penalty):
                return -math.inf
            score += rule.bonus - rule.penalty
        return score

    def _choose_optional_exclusive_candidates(
        self,
        candidates: list[ScoredExpressionUnit],
        optional_weights: Mapping[str, float],
        request: EmotionRequest,
    ) -> list[ScoredExpressionUnit]:
        candidates_by_id = {candidate.unit.id: candidate for candidate in candidates}
        chosen_unit_ids: set[str] = set()
        handled_unit_ids: set[str] = set()

        for rule in self.combination_rules:
            if not rule.any_of_unit_ids or not math.isinf(rule.penalty):
                continue
            group_candidates = [
                candidates_by_id[unit_id]
                for unit_id in rule.any_of_unit_ids
                if unit_id in candidates_by_id and unit_id in optional_weights
            ]
            if len(group_candidates) <= 1:
                continue
            handled_unit_ids.update(candidate.unit.id for candidate in group_candidates)
            chosen = self._choose_one_optional_candidate(group_candidates, request)
            chosen_unit_ids.add(chosen.unit.id)

        return [
            candidate
            for candidate in candidates
            if candidate.unit.id not in handled_unit_ids or candidate.unit.id in chosen_unit_ids
        ]

    def _filter_optional_candidates_by_randomness(
        self,
        candidates: list[ScoredExpressionUnit],
        request: EmotionRequest,
    ) -> list[ScoredExpressionUnit]:
        if request.randomness <= 0.0:
            return candidates

        filtered: list[ScoredExpressionUnit] = []
        for candidate in candidates:
            if self._optional_weight_is_triggered(candidate.template_weight, request):
                filtered.append(candidate)
        return filtered

    def _build_optional_candidates(
        self,
        intent: ExpressionIntent,
        optional_items: tuple[ExpressionIntentOptional, ...],
        unit_candidates: list[ScoredExpressionUnit],
        optional_weights: Mapping[str, float],
        forbidden: set[str],
        request: EmotionRequest,
    ) -> list[OptionalUnitCandidate]:
        _ = optional_weights
        optional_candidates: list[OptionalUnitCandidate] = []
        candidate_unit_ids = {candidate.unit.id for candidate in unit_candidates}

        for item in optional_items:
            if item.weight < 0.2:
                continue
            if request.randomness > 0.0 and not self._optional_weight_is_triggered(
                item.weight,
                request,
            ):
                continue
            item_units = tuple(
                self.units_by_id[unit_id]
                for unit_id in item.units
                if unit_id in self.units_by_id
                and unit_id not in forbidden
                and unit_id not in intent.required_units
                and unit_id in candidate_unit_ids
            )
            if len(item_units) != len(item.units):
                continue
            scored_units = tuple(self._score_unit_for_template(unit, item.weight) for unit in item_units)
            if any(scored.platform_support < 1.0 for scored in scored_units):
                continue
            optional_candidates.append(
                OptionalUnitCandidate(
                    units=item_units,
                    score=sum(scored.score for scored in scored_units),
                    weight=item.weight,
                ),
            )

        return optional_candidates

    def _optional_weight_is_triggered(
        self,
        weight: float,
        request: EmotionRequest,
    ) -> bool:
        exponent = 1.0 + request.randomness * 2.0
        chance = 1.0 - (1.0 - min(1.0, weight)) ** exponent
        return self.rng.random() <= chance

    def _choose_one_optional_candidate(
        self,
        candidates: list[ScoredExpressionUnit],
        request: EmotionRequest,
    ) -> ScoredExpressionUnit:
        ranked = sorted(
            candidates,
            key=lambda candidate: (candidate.template_weight, candidate.score),
            reverse=True,
        )
        if request.randomness <= 0.0:
            return ranked[0]

        weights = [max(0.001, candidate.template_weight * max(0.001, candidate.score)) for candidate in ranked]
        total = sum(weights)
        threshold = self.rng.random() * total
        cumulative = 0.0
        for candidate, weight in zip(ranked, weights, strict=True):
            cumulative += weight
            if cumulative >= threshold:
                return candidate
        return ranked[-1]

    def _history_penalty(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
    ) -> float:
        if not self._recent_expressions or request.history_avoidance <= 0.0:
            return 0.0
        units = tuple(scored.unit for scored in combo)
        targets = self._merge_targets(units, request)
        signature = self._build_signature(units, targets, frozenset(), request)
        max_similarity = 0.0
        total = len(self._recent_expressions)
        for index, recent in enumerate(self._recent_expressions):
            recency = (index + 1) / total
            max_similarity = max(
                max_similarity,
                self._signature_similarity(signature, recent) * recency,
            )
        return max_similarity * request.history_avoidance

    def _merge_targets(
        self,
        units: Iterable[ExpressionUnit],
        request: EmotionRequest,
        *,
        emotion_state: EmotionVectorState | None = None,
        target_offsets: Mapping[str, float] | None = None,
    ) -> tuple[ExpressionTarget, ...]:
        merged: dict[str, tuple[float, float]] = {}
        range_limits: dict[str, tuple[float, float]] = {}
        order: list[str] = []
        offsets = target_offsets or {}
        state = emotion_state or self._emotion_vector_state(request)
        for unit in units:
            for target in self._targets_for_unit(unit, request):
                if target.action not in merged:
                    order.append(target.action)
                    merged[target.action] = (0.0, 0.0)
                if target.value_range is not None:
                    low, high = range_limits.get(target.action, target.value_range)
                    range_limits[target.action] = (
                        max(low, target.value_range[0]),
                        min(high, target.value_range[1]),
                    )
                value = self._resolve_target_value(target, request, state)
                weight = max(0.0, target.weight)
                weighted_value, total_weight = merged[target.action]
                merged[target.action] = (
                    weighted_value + value * weight,
                    total_weight + weight,
                )

        targets: list[ExpressionTarget] = []
        for action in order:
            weighted_value, total_weight = merged[action]
            if total_weight <= 0.0:
                continue
            value = weighted_value / total_weight + offsets.get(action, 0.0)
            if action in range_limits:
                low, high = range_limits[action]
                value = min(max(value, low), high)
            targets.append(
                ExpressionTarget(
                    action=action,
                    value=clamp_semantic_value(action, value),
                ),
            )
        return tuple(targets)

    def _resolve_target_value(
        self,
        target: ExpressionTarget,
        request: EmotionRequest,
        emotion_state: EmotionVectorState,
    ) -> float:
        value = self._sample_target_value(target)
        if target.scale_by_intensity:
            spec = _SEMANTIC_SPECS_BY_ACTION.get(target.action)
            neutral = spec.neutral if spec is not None else 0.0
            value = neutral + (value - neutral) * emotion_state.effective_intensity
            if target.value_range is not None:
                value = min(max(value, target.value_range[0]), target.value_range[1])
        jitter = max(target.jitter, request.value_jitter) * request.randomness
        if jitter > 0.0:
            value += self.rng.uniform(-jitter, jitter)
        if target.value_range is not None:
            value = min(max(value, target.value_range[0]), target.value_range[1])
        return clamp_semantic_value(target.action, value)

    def _sample_target_value(self, target: ExpressionTarget) -> float:
        if target.value_range is None:
            return target.value if target.value is not None else 0.0
        return self.rng.uniform(target.value_range[0], target.value_range[1])

    def _targets_for_unit(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest | None,
    ) -> tuple[ExpressionTarget, ...]:
        _ = request
        return unit.targets

    def _dominant_emotion(self, request: EmotionRequest) -> EmotionKind:
        return max(request.emotions.items(), key=lambda item: item[1])[0]

    def _units_by_region(
        self,
        units: tuple[ExpressionUnit, ...],
    ) -> dict[ExpressionRegion, tuple[ExpressionUnit, ...]]:
        by_region: dict[ExpressionRegion, list[ExpressionUnit]] = {}
        for unit in units:
            for region in unit.regions:
                by_region.setdefault(region, []).append(unit)
        return {region: tuple(region_units) for region, region_units in by_region.items()}

    def _build_signature(
        self,
        units: tuple[ExpressionUnit, ...],
        targets: tuple[ExpressionTarget, ...],
        semantic_tags: frozenset[str],
        request: EmotionRequest,
    ) -> ExpressionSignature:
        return ExpressionSignature(
            unit_ids=tuple(unit.id for unit in units),
            target_values={target.action: target.value for target in targets},
            semantic_tags=semantic_tags,
            dominant_emotion=self._dominant_emotion(request),
            intensity=request.intensity,
        )

    def _signature_similarity(
        self,
        current: ExpressionSignature,
        recent: ExpressionSignature,
    ) -> float:
        current_units = set(current.unit_ids)
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
                    1.0 - abs(current.target_values[action] - recent.target_values[action]) / 2.0,
                )
                for action in shared_actions
            ) / len(shared_actions)
        else:
            target_similarity = 0.0

        shared_tags = current.semantic_tags & recent.semantic_tags
        tag_similarity = len(shared_tags) / max(
            len(current.semantic_tags | recent.semantic_tags),
            1,
        )
        emotion_similarity = 1.0 if current.dominant_emotion is recent.dominant_emotion else 0.0
        intensity_similarity = max(0.0, 1.0 - abs(current.intensity - recent.intensity))
        return (
            unit_similarity * 0.35
            + target_similarity * 0.25
            + tag_similarity * 0.20
            + emotion_similarity * 0.10
            + intensity_similarity * 0.10
        )

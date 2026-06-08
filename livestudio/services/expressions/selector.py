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
    SemanticActionTarget,
    clamp_semantic_value,
)

from .intents import BUILTIN_EXPRESSION_INTENTS, ExpressionIntent
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


@dataclass(frozen=True, slots=True)
class EmotionVectorState:
    composition: Mapping[EmotionKind, float]
    energy: float
    effective_intensity: float
    explicit_intent: bool


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
        combination_rules: Iterable[
            ExpressionCombinationRule
        ] = BUILTIN_COMBINATION_RULES,
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

        scored = [
            (self._score_intent(intent, request, emotion_state), intent)
            for intent in self.intents
        ]
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
                max(0.0, expected.get(emotion, 0.0))
                - max(0.0, actual.get(emotion, 0.0)),
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
            expressive = {EmotionKind.NEUTRAL: max(0.0, request.emotions.get(EmotionKind.NEUTRAL, 1.0))}

        total = sum(expressive.values())
        composition = (
            {emotion: value / total for emotion, value in expressive.items()}
            if total > 0.0
            else {EmotionKind.NEUTRAL: 1.0}
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
        required_units = [
            self.units_by_id[unit_id]
            for unit_id in intent.required_units
            if unit_id in self.units_by_id
        ]
        if len(required_units) != len(intent.required_units):
            return 0.0
        return self.semantic_profile.support_score(
            SemanticActionTarget(target.action, 0.0, target.weight)
            for unit in required_units
            for target in unit.targets
        )

    def _select_from_intent(
        self,
        intent: ExpressionIntent,
        request: EmotionRequest,
        emotion_state: EmotionVectorState,
    ) -> SelectedExpression:
        missing = [
            unit_id
            for unit_id in intent.required_units
            if unit_id not in self.units_by_id
        ]
        if missing:
            raise ValueError(
                f"intent {intent.id} references unknown required units: {', '.join(missing)}",
            )

        required = [self.units_by_id[unit_id] for unit_id in intent.required_units]
        forbidden = set(intent.forbidden_units)
        variant_strengths = self._intent_variant_strengths(intent, emotion_state)
        optional_weights = self._intent_optional_weights(intent, variant_strengths)
        candidates = [
            self._score_unit_for_template(unit, optional_weights.get(unit.id, 0.0))
            for unit in self.units
            if unit.id not in forbidden and unit.id not in intent.required_units
        ]
        candidates = [
            candidate
            for candidate in candidates
            if candidate.platform_support >= 1.0 and candidate.template_weight >= 0.2
        ]
        candidates.sort(
            key=lambda candidate: (
                optional_weights.get(candidate.unit.id, 0.0),
                candidate.score,
            ),
            reverse=True,
        )

        selected_units = list(required)
        for candidate in candidates:
            if len(selected_units) >= request.max_units:
                break
            if candidate.unit.id not in optional_weights:
                continue
            trial_units = (*selected_units, candidate.unit)
            trial_scored = tuple(
                self._score_unit_for_template(
                    unit,
                    1.0
                    if unit.id in intent.required_units
                    else optional_weights.get(unit.id, 0.0),
                )
                for unit in trial_units
            )
            if math.isfinite(self._score_combo(trial_scored, request)):
                selected_units.append(candidate.unit)

        scored_combo = tuple(
            self._score_unit_for_template(
                unit,
                1.0
                if unit.id in intent.required_units
                else optional_weights.get(unit.id, 0.0),
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
        action_tags = frozenset().union(*(unit.action_tags for unit in units))
        semantic_tags = frozenset(
            {
                self._dominant_emotion(request).value,
                intent.id,
                *intent.output_tags,
                *intent.style_tags,
                *self._intent_variant_tags(intent, variant_strengths),
                *action_tags,
            },
        )

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
            strengths[variant.id] = max(0.0, min(1.0, delta * emotion_state.energy * 4.0))
        return strengths

    def _normalized_emotions(
        self,
        emotions: Mapping[EmotionKind, float],
    ) -> dict[EmotionKind, float]:
        values = {
            emotion: max(0.0, value)
            for emotion, value in emotions.items()
            if value > 0.0
        }
        total = sum(values.values())
        if total <= 0.0:
            return {EmotionKind.NEUTRAL: 1.0}
        return {emotion: value / total for emotion, value in values.items()}

    def _intent_optional_weights(
        self,
        intent: ExpressionIntent,
        variant_strengths: Mapping[str, float],
    ) -> dict[str, float]:
        weights = dict(intent.optional_units)
        variants_by_id = {variant.id: variant for variant in intent.variants}
        for variant_id, strength in variant_strengths.items():
            variant = variants_by_id[variant_id]
            for unit_id, adjustment in variant.optional_unit_adjustments.items():
                weights[unit_id] = max(
                    0.0,
                    weights.get(unit_id, 0.0) + adjustment * strength,
                )
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

    def _intent_variant_tags(
        self,
        intent: ExpressionIntent,
        variant_strengths: Mapping[str, float],
    ) -> frozenset[str]:
        tags: set[str] = set()
        variants_by_id = {variant.id: variant for variant in intent.variants}
        for variant_id, strength in variant_strengths.items():
            if strength <= 0.0:
                continue
            tags.update(variants_by_id[variant_id].style_tags)
        return frozenset(tags)

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
    ) -> tuple[SemanticActionTarget, ...]:
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
        platform_support = self.semantic_profile.support_score(
            SemanticActionTarget(target.action, 0.0, target.weight)
            for target in target_tuple
        )
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
            action_tags=unit.action_tags,
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
        tags = frozenset().union(*(scored.action_tags for scored in combo))
        for scored in combo:
            other_tags = set().union(
                *(
                    other.action_tags
                    for other in combo
                    if other.unit.id != scored.unit.id
                ),
            )
            other_unit_ids = unit_ids - {scored.unit.id}
            if scored.unit.conflicts.intersection(
                other_tags,
            ) or scored.unit.conflicts.intersection(other_unit_ids):
                return -math.inf

        rule_penalty = self._combination_rule_penalty(unit_ids, tags, request)
        if math.isinf(rule_penalty):
            return -math.inf

        score = sum(scored.score for scored in combo)
        score -= rule_penalty
        score += self._coverage_score(combo) * 0.18
        score += self._synergy_score(combo) * 0.10
        score -= self._soft_conflict_penalty(combo)
        score -= self._history_penalty(combo, request)
        score -= max(0, len(combo) - 1) * 0.08
        return score

    def _coverage_score(self, combo: tuple[ScoredExpressionUnit, ...]) -> float:
        regions = set().union(*(scored.unit.regions for scored in combo))
        tags = set().union(*(scored.action_tags for scored in combo))
        return min(1.0, len(regions) / 4.0) * 0.6 + min(1.0, len(tags) / 6.0) * 0.4

    def _synergy_score(self, combo: tuple[ScoredExpressionUnit, ...]) -> float:
        unit_ids = {scored.unit.id for scored in combo}
        tags = set().union(*(scored.action_tags for scored in combo))
        score = 0.0
        for scored in combo:
            score += sum(
                bonus
                for target_id, bonus in scored.unit.synergies.items()
                if target_id in unit_ids or target_id in tags
            )
        return score

    def _soft_conflict_penalty(self, combo: tuple[ScoredExpressionUnit, ...]) -> float:
        unit_ids = {scored.unit.id for scored in combo}
        tags = set().union(*(scored.action_tags for scored in combo))
        penalty = 0.0
        for scored in combo:
            penalty += sum(
                value
                for target_id, value in scored.unit.soft_conflicts.items()
                if target_id in unit_ids or target_id in tags
            )
        return penalty

    def _combination_rule_penalty(
        self,
        unit_ids: set[str],
        tags: frozenset[str],
        request: EmotionRequest,
    ) -> float:
        penalty = 0.0
        active_emotions = {
            emotion for emotion, weight in request.emotions.items() if weight > 0.0
        }
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
            penalty += rule.penalty
        return penalty

    def _history_penalty(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
    ) -> float:
        if not self._recent_expressions or request.history_avoidance <= 0.0:
            return 0.0
        units = tuple(scored.unit for scored in combo)
        targets = self._merge_targets(units, request)
        tags = frozenset().union(*(scored.action_tags for scored in combo))
        signature = self._build_signature(units, targets, tags, request)
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
    ) -> tuple[SemanticActionTarget, ...]:
        merged: dict[str, tuple[float, float]] = {}
        order: list[str] = []
        offsets = target_offsets or {}
        state = emotion_state or self._emotion_vector_state(request)
        for unit in units:
            for target in self._targets_for_unit(unit, request):
                if target.action not in merged:
                    order.append(target.action)
                    merged[target.action] = (0.0, 0.0)
                value = self._resolve_target_value(target, request, state)
                weight = max(0.0, target.weight)
                weighted_value, total_weight = merged[target.action]
                merged[target.action] = (
                    weighted_value + value * weight,
                    total_weight + weight,
                )

        return tuple(
            SemanticActionTarget(
                action=action,
                value=clamp_semantic_value(
                    action,
                    weighted_value / total_weight + offsets.get(action, 0.0),
                ),
            )
            for action in order
            for weighted_value, total_weight in (merged[action],)
            if total_weight > 0.0
        )

    def _resolve_target_value(
        self,
        target: ExpressionTarget,
        request: EmotionRequest,
        emotion_state: EmotionVectorState,
    ) -> float:
        value = self._sample_target_value(target)
        if target.scale_by_intensity:
            spec = DEFAULT_SEMANTIC_ACTION_SPECS.get(target.action)
            neutral = spec.neutral if spec is not None else 0.0
            value = neutral + (value - neutral) * emotion_state.effective_intensity
        jitter = max(target.jitter, request.value_jitter) * request.randomness
        if jitter > 0.0:
            value += self.rng.uniform(-jitter, jitter)
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
        return {
            region: tuple(region_units) for region, region_units in by_region.items()
        }

    def _build_signature(
        self,
        units: tuple[ExpressionUnit, ...],
        targets: tuple[SemanticActionTarget, ...],
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
                    1.0
                    - abs(current.target_values[action] - recent.target_values[action])
                    / 2.0,
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
        emotion_similarity = (
            1.0 if current.dominant_emotion is recent.dominant_emotion else 0.0
        )
        intensity_similarity = max(0.0, 1.0 - abs(current.intensity - recent.intensity))
        return (
            unit_similarity * 0.35
            + target_similarity * 0.25
            + tag_similarity * 0.20
            + emotion_similarity * 0.10
            + intensity_similarity * 0.10
        )

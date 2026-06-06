"""按情绪挑表情动作的选择器"""

from __future__ import annotations

import math
import random
from collections import deque
from collections.abc import Iterable

from livestudio.services.semantic_actions import (
    DEFAULT_SEMANTIC_ACTION_SPECS,
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
    ExpressionTarget,
    ExpressionUnit,
    ScoredExpressionUnit,
    SelectedExpression,
)
from .rules import BUILTIN_COMBINATION_RULES


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
        combination_rules: Iterable[
            ExpressionCombinationRule
        ] = BUILTIN_COMBINATION_RULES,
    ) -> None:
        self.units = tuple(units)
        self.semantic_profile = semantic_profile
        self.rng = rng or random.Random()
        self.top_candidates = top_candidates
        self.beam_width = beam_width
        self._recent_unit_ids: deque[str] = deque(maxlen=recent_size)
        self._recent_expressions: deque[ExpressionSignature] = deque(maxlen=recent_size)
        self.combination_rules = tuple(combination_rules)

    def select(self, request: EmotionRequest) -> SelectedExpression:
        candidates = self._rank_candidates(request)
        if not candidates:
            raise ValueError("no expression units are available for selection")

        scored_combos = self._build_combos(candidates, request)
        if not scored_combos:
            raise ValueError("no compatible expression unit combinations are available")

        scored_combos.sort(key=lambda item: item[0], reverse=True)
        selected_score, selected_combo = self._sample_combo(scored_combos, request)
        targets = self._merge_targets((scored.unit for scored in selected_combo), request)
        tags = self._collect_tags(selected_combo, request)
        semantic_tags = frozenset().union(*tags.values()) if tags else frozenset()
        dominant_emotion = self._dominant_emotion(request)
        semantic_tags = frozenset({dominant_emotion.value, *semantic_tags})
        units = tuple(scored.unit for scored in selected_combo)

        for unit in units:
            self._recent_unit_ids.append(unit.id)
        self._recent_expressions.append(
            self._build_signature(units, targets, semantic_tags, request),
        )

        return SelectedExpression(
            units=units,
            units_by_region=self._units_by_region(units),
            score=selected_score,
            emotion_match=self._combo_emotion_match(selected_combo),
            intent_strength=max((scored.intent_strength for scored in selected_combo), default=0.0),
            tags=tags,
            semantic_tags=semantic_tags,
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

    def _rank_candidates(self, request: EmotionRequest) -> list[ScoredExpressionUnit]:
        candidates = [self._score_unit(unit, request) for unit in self.units]
        candidates = [
            candidate
            for candidate in candidates
            if candidate.platform_support >= 1.0
            and candidate.intent_strength >= self._effective_min_intent_score(request)
        ]
        candidates.sort(key=lambda candidate: candidate.score, reverse=True)
        return candidates[: self.top_candidates]

    def _effective_min_intent_score(self, request: EmotionRequest) -> float:
        expressive_weight = max(
            (
                weight
                for emotion, weight in request.emotions.items()
                if emotion is not EmotionKind.NEUTRAL
            ),
            default=0.0,
        )
        if expressive_weight <= 0.0:
            return 0.0
        return request.min_intent_score * expressive_weight

    def _score_unit(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest,
    ) -> ScoredExpressionUnit:
        emotion_match = sum(
            request_weight * unit.emotions.get(emotion, _EMPTY_PROFILE).weight
            for emotion, request_weight in request.emotions.items()
        )
        target_tuple = self._targets_for_unit(unit, request)
        platform_support = self.semantic_profile.support_score(
            SemanticActionTarget(target.action, 0.0, target.weight)
            for target in target_tuple
        )
        intensity_match = self._intensity_match(unit, request)
        novelty = 0.3 if unit.id in self._recent_unit_ids else 1.0
        tags = self._tags_for_unit(unit, request)
        intent_strength = emotion_match * max(0.25, intensity_match)
        score = (
            intent_strength * 0.52
            + platform_support * 0.16
            + unit.naturalness * 0.12
            + unit.base_weight * 0.08
            + min(1.0, len(tags) / 4.0) * 0.07
            + novelty * 0.05
        )
        return ScoredExpressionUnit(
            unit=unit,
            score=max(0.0, score),
            emotion_match=emotion_match,
            intent_strength=intent_strength,
            platform_support=platform_support,
            tags=tags,
        )

    def _build_combos(
        self,
        candidates: list[ScoredExpressionUnit],
        request: EmotionRequest,
    ) -> list[tuple[float, tuple[ScoredExpressionUnit, ...]]]:
        beams: list[tuple[float, tuple[ScoredExpressionUnit, ...]]] = [(0.0, ())]
        completed: list[tuple[float, tuple[ScoredExpressionUnit, ...]]] = []

        for _ in range(request.max_units):
            expanded: list[tuple[float, tuple[ScoredExpressionUnit, ...]]] = []
            for _, combo in beams:
                used_ids = {scored.unit.id for scored in combo}
                for candidate in candidates:
                    if candidate.unit.id in used_ids:
                        continue
                    new_combo = (*combo, candidate)
                    score = self._score_combo(new_combo, request)
                    if math.isfinite(score):
                        expanded.append((score, new_combo))
            if not expanded:
                break
            expanded.sort(key=lambda item: item[0], reverse=True)
            beams = expanded[: self.beam_width]
            completed.extend(beams)

        best_by_signature: dict[tuple[str, ...], tuple[float, tuple[ScoredExpressionUnit, ...]]] = {}
        for score, combo in completed:
            signature = tuple(sorted(scored.unit.id for scored in combo))
            if signature not in best_by_signature or score > best_by_signature[signature][0]:
                best_by_signature[signature] = (score, combo)
        return list(best_by_signature.values())

    def _score_combo(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
    ) -> float:
        if not combo:
            return -math.inf

        unit_ids = {scored.unit.id for scored in combo}
        tags = frozenset().union(*(scored.tags for scored in combo))
        for scored in combo:
            other_tags = set().union(
                *(other.tags for other in combo if other.unit.id != scored.unit.id),
            )
            other_unit_ids = unit_ids - {scored.unit.id}
            if scored.unit.conflicts.intersection(other_tags) or scored.unit.conflicts.intersection(other_unit_ids):
                return -math.inf

        rule_penalty = self._combination_rule_penalty(unit_ids, tags, request)
        if math.isinf(rule_penalty):
            return -math.inf

        score = sum(scored.score for scored in combo)
        score -= rule_penalty
        score += self._coverage_score(combo) * 0.18
        score += self._synergy_score(combo) * 0.10
        score -= self._soft_conflict_penalty(combo)
        score -= self._target_collision_penalty(combo, request)
        score -= self._history_penalty(combo, request)
        score -= max(0, len(combo) - 1) * 0.08
        return score

    def _coverage_score(self, combo: tuple[ScoredExpressionUnit, ...]) -> float:
        regions = set().union(*(scored.unit.regions for scored in combo))
        tags = set().union(*(scored.tags for scored in combo))
        return min(1.0, len(regions) / 4.0) * 0.6 + min(1.0, len(tags) / 6.0) * 0.4

    def _synergy_score(self, combo: tuple[ScoredExpressionUnit, ...]) -> float:
        unit_ids = {scored.unit.id for scored in combo}
        tags = set().union(*(scored.tags for scored in combo))
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
        tags = set().union(*(scored.tags for scored in combo))
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
            emotion
            for emotion, weight in request.emotions.items()
            if weight > 0.0
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

    def _target_collision_penalty(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
    ) -> float:
        values: dict[str, list[float]] = {}
        for scored in combo:
            for target in self._targets_for_unit(scored.unit, request):
                values.setdefault(target.action, []).append(self._target_base_value(target))
        penalty = 0.0
        for action_values in values.values():
            if len(action_values) <= 1:
                continue
            penalty += (max(action_values) - min(action_values)) * 0.25
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
        tags = frozenset().union(*(scored.tags for scored in combo))
        signature = self._build_signature(units, targets, tags, request)
        max_similarity = 0.0
        total = len(self._recent_expressions)
        for index, recent in enumerate(self._recent_expressions):
            recency = (index + 1) / total
            max_similarity = max(max_similarity, self._signature_similarity(signature, recent) * recency)
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
        request: EmotionRequest,
    ) -> tuple[SemanticActionTarget, ...]:
        merged: dict[str, tuple[float, float]] = {}
        order: list[str] = []
        for unit in units:
            for target in self._targets_for_unit(unit, request):
                if target.action not in merged:
                    order.append(target.action)
                    merged[target.action] = (0.0, 0.0)
                value = self._resolve_target_value(target, request)
                weight = max(0.0, target.weight)
                weighted_value, total_weight = merged[target.action]
                merged[target.action] = (weighted_value + value * weight, total_weight + weight)

        return tuple(
            SemanticActionTarget(action=action, value=clamp_semantic_value(action, weighted_value / total_weight))
            for action in order
            for weighted_value, total_weight in (merged[action],)
            if total_weight > 0.0
        )

    def _resolve_target_value(
        self,
        target: ExpressionTarget,
        request: EmotionRequest,
    ) -> float:
        value = self._sample_target_value(target)
        if target.scale_by_intensity:
            spec = DEFAULT_SEMANTIC_ACTION_SPECS.get(target.action)
            neutral = spec.neutral if spec is not None else 0.0
            value = neutral + (value - neutral) * request.intensity
        jitter = max(target.jitter, request.value_jitter) * request.randomness
        if jitter > 0.0:
            value += self.rng.uniform(-jitter, jitter)
        return clamp_semantic_value(target.action, value)

    def _sample_target_value(self, target: ExpressionTarget) -> float:
        if target.value_range is None:
            return target.value if target.value is not None else 0.0
        return self.rng.uniform(target.value_range[0], target.value_range[1])

    def _target_base_value(self, target: ExpressionTarget) -> float:
        if target.value_range is None:
            return target.value if target.value is not None else 0.0
        return (target.value_range[0] + target.value_range[1]) / 2.0

    def _targets_for_unit(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest,
    ) -> tuple[ExpressionTarget, ...]:
        return unit.targets

    def _tags_for_unit(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest,
    ) -> frozenset[str]:
        tags = set(unit.global_tags)
        for emotion in request.emotions:
            profile = unit.emotions.get(emotion)
            if profile is not None:
                tags.update(profile.tags)
        return frozenset(tags)

    def _collect_tags(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
    ) -> dict[EmotionKind, frozenset[str]]:
        tags: dict[EmotionKind, set[str]] = {}
        for scored in combo:
            for emotion in request.emotions:
                profile = scored.unit.emotions.get(emotion)
                if profile is None:
                    continue
                tags.setdefault(emotion, set()).update(profile.tags)
        return {emotion: frozenset(values) for emotion, values in tags.items()}

    def _intensity_match(self, unit: ExpressionUnit, request: EmotionRequest) -> float:
        matches: list[float] = []
        for emotion, weight in request.emotions.items():
            profile = unit.emotions.get(emotion)
            if profile is None:
                continue
            expected = profile.intensity if profile.intensity is not None else request.intensity
            matches.append((1.0 - abs(request.intensity - expected)) * weight)
        if not matches:
            return 0.0
        total_weight = sum(request.emotions.values()) or 1.0
        return max(0.0, min(1.0, sum(matches) / total_weight))

    def _combo_emotion_match(self, combo: tuple[ScoredExpressionUnit, ...]) -> float:
        if not combo:
            return 0.0
        return sum(scored.emotion_match for scored in combo) / len(combo)

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
        unit_similarity = len(current_units & recent_units) / max(len(current_units | recent_units), 1)

        shared_actions = set(current.target_values).intersection(recent.target_values)
        if shared_actions:
            target_similarity = sum(
                max(0.0, 1.0 - abs(current.target_values[action] - recent.target_values[action]) / 2.0)
                for action in shared_actions
            ) / len(shared_actions)
        else:
            target_similarity = 0.0

        shared_tags = current.semantic_tags & recent.semantic_tags
        tag_similarity = len(shared_tags) / max(len(current.semantic_tags | recent.semantic_tags), 1)
        emotion_similarity = 1.0 if current.dominant_emotion is recent.dominant_emotion else 0.0
        intensity_similarity = max(0.0, 1.0 - abs(current.intensity - recent.intensity))
        return (
            unit_similarity * 0.35
            + target_similarity * 0.25
            + tag_similarity * 0.20
            + emotion_similarity * 0.10
            + intensity_similarity * 0.10
        )


_EMPTY_PROFILE = type("_EmptyEmotionProfile", (), {"weight": 0.0})()

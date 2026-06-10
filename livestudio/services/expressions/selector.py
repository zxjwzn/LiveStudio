"""按单个情绪强度解算 AU 组合的选择器"""

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

from .models import (
    EmotionKind,
    EmotionRequest,
    ExpressionCombinationRule,
    ExpressionRegion,
    ExpressionRuleKind,
    ExpressionSignature,
    ExpressionTarget,
    ExpressionUnit,
    ScoredExpressionUnit,
    SelectedExpression,
    units_by_region,
)
from .rules import BUILTIN_COMBINATION_RULES


@dataclass(frozen=True, slots=True)
class EmotionSolverState:
    emotion: EmotionKind
    strength: float
    effective_intensity: float


class ExpressionSelector:
    """根据一个归一化情绪强度，从 AU 相关性和规则中解算表情"""

    def __init__(
        self,
        units: Iterable[ExpressionUnit],
        semantic_profile: SemanticActionProfile,
        *,
        rng: random.Random | None = None,
        top_candidates: int = 14,
        recent_size: int = 16,
        combination_rules: Iterable[
            ExpressionCombinationRule
        ] = BUILTIN_COMBINATION_RULES,
    ) -> None:
        self.units = tuple(units)
        self.units_by_id = {unit.id: unit for unit in self.units}
        self.semantic_profile = semantic_profile
        self.rng = rng or random.Random()
        self.top_candidates = top_candidates
        self._recent_unit_ids: deque[str] = deque(maxlen=recent_size)
        self._recent_expressions: deque[ExpressionSignature] = deque(maxlen=recent_size)
        self.combination_rules = tuple(combination_rules)

    def select(self, request: EmotionRequest) -> SelectedExpression:
        state = self._emotion_solver_state(request)
        candidates = self._score_candidates(request, state)
        selected_scored = self._select_scored_units(candidates, request, state)
        if not selected_scored:
            raise ValueError(f"no AU candidates match emotion {state.emotion.value}")

        combo_score = self._score_combo(selected_scored, request, state)
        if not math.isfinite(combo_score):
            raise ValueError(
                f"cannot build a compatible AU expression for {state.emotion.value}"
            )

        targets = self._merge_scored_targets(selected_scored, request, state)
        units = tuple(scored.unit for scored in selected_scored)
        semantic_tags = frozenset({state.emotion.value, "au_solver"})

        for unit in units:
            self._recent_unit_ids.append(unit.id)
        self._recent_expressions.append(
            self._build_signature(units, targets, semantic_tags, request, state),
        )

        return SelectedExpression(
            units=units,
            emotion=state.emotion,
            units_by_region=units_by_region(units),
            score=combo_score,
            emotion_match=max(
                (scored.correlation for scored in selected_scored), default=0.0
            ),
            expression_strength=state.effective_intensity,
            semantic_tags=semantic_tags,
            targets=targets,
        )

    def preview(self, request: EmotionRequest) -> SelectedExpression:
        unit_state = tuple(self._recent_unit_ids)
        expression_state = tuple(self._recent_expressions)
        rng_state = self.rng.getstate()
        try:
            return self.select(request)
        finally:
            self._recent_unit_ids.clear()
            self._recent_unit_ids.extend(unit_state)
            self._recent_expressions.clear()
            self._recent_expressions.extend(expression_state)
            self.rng.setstate(rng_state)

    def merge_unit_targets(
        self,
        units: Iterable[ExpressionUnit],
        request: EmotionRequest | None = None,
    ) -> tuple[SemanticActionTarget, ...]:
        resolved_request = request or EmotionRequest(
            emotions={EmotionKind.NEUTRAL: 1.0},
            intensity=1.0,
            randomness=0.0,
            diversity=0.0,
            history_avoidance=0.0,
        )
        state = self._emotion_solver_state(resolved_request)
        scored_units = tuple(
            ScoredExpressionUnit(
                unit=unit,
                score=1.0,
                activation=1.0,
                correlation=max(0.0, unit.correlation_for(state.emotion)),
                platform_support=self._platform_support(unit),
            )
            for unit in units
        )
        return self._merge_scored_targets(scored_units, resolved_request, state)

    def _emotion_solver_state(self, request: EmotionRequest) -> EmotionSolverState:
        strength = request.emotion_strength
        effective_intensity = request.intensity * strength
        return EmotionSolverState(
            emotion=request.emotion,
            strength=strength,
            effective_intensity=effective_intensity,
        )

    def _score_candidates(
        self,
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> list[ScoredExpressionUnit]:
        candidates: list[ScoredExpressionUnit] = []
        for unit in self.units:
            scored = self._score_unit(unit, request, state)
            if scored is None:
                continue
            candidates.append(scored)

        candidates.sort(key=lambda scored: scored.score, reverse=True)
        return candidates[: self.top_candidates]

    def _score_unit(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> ScoredExpressionUnit | None:
        platform_support = self._platform_support(unit)
        if platform_support < 1.0:
            return None

        correlation = unit.correlation_for(state.emotion)
        if correlation <= 0.0:
            return None

        activation_input = correlation * state.effective_intensity
        if activation_input <= unit.activation_threshold:
            return None

        denominator = max(1e-6, 1.0 - unit.activation_threshold)
        activation = max(
            0.0, min(1.0, (activation_input - unit.activation_threshold) / denominator)
        )
        if activation <= 0.0:
            return None

        novelty = 0.35 if unit.id in self._recent_unit_ids else 1.0
        score = (
            activation * 0.52
            + correlation * 0.18
            + unit.naturalness * 0.12
            + unit.base_weight * 0.08
            + platform_support * 0.05
            + novelty * 0.05
        )
        score *= unit.base_weight
        score -= self._unit_history_penalty(unit, request, state)

        if score < request.min_au_score:
            return None

        return ScoredExpressionUnit(
            unit=unit,
            score=max(0.0, score),
            activation=activation,
            correlation=correlation,
            platform_support=platform_support,
        )

    def _platform_support(self, unit: ExpressionUnit) -> float:
        return self.semantic_profile.support_score(
            SemanticActionTarget(target.action, 0.0, target.weight)
            for target in unit.targets
        )

    def _unit_history_penalty(
        self,
        unit: ExpressionUnit,
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> float:
        if request.history_avoidance <= 0.0 or not self._recent_expressions:
            return 0.0

        recency_weight = 0.0
        total = len(self._recent_expressions)
        for index, signature in enumerate(self._recent_expressions):
            if (
                signature.emotion is not state.emotion
                or unit.id not in signature.unit_ids
            ):
                continue
            recency_weight = max(recency_weight, (index + 1) / total)
        return recency_weight * request.history_avoidance * 0.18

    def _select_scored_units(
        self,
        candidates: list[ScoredExpressionUnit],
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> tuple[ScoredExpressionUnit, ...]:
        selected: list[ScoredExpressionUnit] = []
        ordered = sorted(
            candidates,
            key=lambda scored: self._selection_rank(scored, request),
            reverse=True,
        )

        for candidate in ordered:
            if len(selected) >= request.max_units:
                break
            if not self._should_select_candidate(candidate, request):
                continue
            resolved = self._resolve_mutex_conflicts(selected, candidate)
            if resolved is None:
                continue
            trial = [*resolved, candidate]
            if not math.isfinite(self._score_combo(tuple(trial), request, state)):
                continue
            selected = trial

        if selected:
            return tuple(
                sorted(selected, key=lambda scored: scored.score, reverse=True)
            )
        return tuple(candidates[:1])

    def _selection_rank(
        self, scored: ScoredExpressionUnit, request: EmotionRequest
    ) -> float:
        if request.randomness <= 0.0:
            return scored.score
        noise = (
            self.rng.uniform(-1.0, 1.0) * request.randomness * request.diversity * 0.25
        )
        return scored.score + noise

    def _should_select_candidate(
        self,
        scored: ScoredExpressionUnit,
        request: EmotionRequest,
    ) -> bool:
        if scored.score >= request.core_score or scored.activation >= 0.66:
            return True
        if request.randomness <= 0.0:
            return True
        probability = min(
            1.0,
            max(0.05, scored.score) * (0.55 + request.diversity * 0.55)
            + scored.activation * 0.25,
        )
        return self.rng.random() <= probability

    def _resolve_mutex_conflicts(
        self,
        selected: list[ScoredExpressionUnit],
        candidate: ScoredExpressionUnit,
    ) -> list[ScoredExpressionUnit] | None:
        resolved = list(selected)
        for rule in self.combination_rules:
            if rule.kind is not ExpressionRuleKind.MUTEX:
                continue
            if candidate.unit.id not in rule.unit_ids:
                continue
            conflicts = [
                scored for scored in resolved if scored.unit.id in rule.unit_ids
            ]
            for conflict in conflicts:
                if self._candidate_beats_conflict(candidate, conflict):
                    resolved.remove(conflict)
                    continue
                return None
        return resolved

    def _candidate_beats_conflict(
        self,
        candidate: ScoredExpressionUnit,
        conflict: ScoredExpressionUnit,
    ) -> bool:
        if candidate.score > conflict.score + 0.03:
            return True
        if abs(candidate.score - conflict.score) <= 0.03:
            return candidate.unit.priority > conflict.unit.priority
        return False

    def _score_combo(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> float:
        if not combo:
            return -math.inf

        unit_ids = {scored.unit.id for scored in combo}
        score = sum(scored.score for scored in combo)
        score += self._coverage_score(combo) * 0.14
        score -= max(0, len(combo) - 1) * 0.06
        score += self._combination_rule_score(unit_ids, state)
        if not math.isfinite(score):
            return -math.inf
        score -= self._history_penalty(combo, request, state)
        return score

    def _coverage_score(self, combo: tuple[ScoredExpressionUnit, ...]) -> float:
        regions = set().union(*(scored.unit.regions for scored in combo))
        return min(1.0, len(regions) / 4.0)

    def _combination_rule_score(
        self,
        unit_ids: set[str],
        state: EmotionSolverState,
    ) -> float:
        score = 0.0
        for rule in self.combination_rules:
            if rule.emotions and state.emotion not in rule.emotions:
                continue
            if rule.kind is ExpressionRuleKind.MUTEX:
                if len(unit_ids & rule.unit_ids) > 1:
                    return -math.inf
                continue
            if rule.kind is ExpressionRuleKind.SYNERGY:
                if rule.unit_ids and rule.unit_ids.issubset(unit_ids):
                    score += rule.bonus
                continue
            if rule.kind is ExpressionRuleKind.SUPPRESSION:
                if rule.source_unit_id in unit_ids and rule.target_unit_id in unit_ids:
                    score -= max(rule.penalty, rule.strength)
                continue
            if rule.kind is ExpressionRuleKind.DEPENDENCY:
                if (
                    rule.source_unit_id in unit_ids
                    and rule.target_unit_id not in unit_ids
                ):
                    if math.isinf(rule.penalty):
                        return -math.inf
                    score -= rule.penalty
                continue
            if rule.kind is ExpressionRuleKind.PRESERVE and rule.unit_ids.intersection(
                unit_ids
            ):
                score += rule.bonus
        return score

    def _history_penalty(
        self,
        combo: tuple[ScoredExpressionUnit, ...],
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> float:
        if not self._recent_expressions or request.history_avoidance <= 0.0:
            return 0.0
        units = tuple(scored.unit for scored in combo)
        targets = self._merge_scored_targets(combo, request, state)
        signature = self._build_signature(units, targets, frozenset(), request, state)
        max_similarity = 0.0
        total = len(self._recent_expressions)
        for index, recent in enumerate(self._recent_expressions):
            recency = (index + 1) / total
            max_similarity = max(
                max_similarity,
                self._signature_similarity(signature, recent) * recency,
            )
        return max_similarity * request.history_avoidance

    def _merge_scored_targets(
        self,
        scored_units: Iterable[ScoredExpressionUnit],
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> tuple[SemanticActionTarget, ...]:
        merged: dict[str, tuple[float, float]] = {}
        range_limits: dict[str, tuple[float, float]] = {}
        order: list[str] = []
        for scored in scored_units:
            for target in scored.unit.targets:
                if target.action not in merged:
                    order.append(target.action)
                    merged[target.action] = (0.0, 0.0)
                if target.value_range is not None:
                    low, high = range_limits.get(target.action, target.value_range)
                    range_limits[target.action] = (
                        max(low, target.value_range[0]),
                        min(high, target.value_range[1]),
                    )
                value = self._resolve_target_value(
                    target, scored.activation, request, state
                )
                weight = max(0.0, target.weight) * max(0.05, scored.activation)
                weighted_value, total_weight = merged[target.action]
                merged[target.action] = (
                    weighted_value + value * weight,
                    total_weight + weight,
                )

        targets: list[SemanticActionTarget] = []
        for action in order:
            weighted_value, total_weight = merged[action]
            if total_weight <= 0.0:
                continue
            value = weighted_value / total_weight
            if action in range_limits:
                low, high = range_limits[action]
                value = min(max(value, low), high)
            targets.append(
                SemanticActionTarget(
                    action=action, value=clamp_semantic_value(action, value)
                )
            )
        return tuple(targets)

    def _resolve_target_value(
        self,
        target: ExpressionTarget,
        activation: float,
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> float:
        value = self._sample_target_value(target)
        if target.scale_by_intensity:
            spec = DEFAULT_SEMANTIC_ACTION_SPECS.get(target.action)
            neutral = spec.neutral if spec is not None else 0.0
            intensity = max(0.0, min(1.0, activation * state.effective_intensity))
            value = neutral + (value - neutral) * intensity
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

    def _build_signature(
        self,
        units: tuple[ExpressionUnit, ...],
        targets: tuple[SemanticActionTarget, ...],
        semantic_tags: frozenset[str],
        request: EmotionRequest,
        state: EmotionSolverState,
    ) -> ExpressionSignature:
        _ = request
        return ExpressionSignature(
            unit_ids=tuple(unit.id for unit in units),
            target_values={target.action: target.value for target in targets},
            semantic_tags=semantic_tags,
            emotion=state.emotion,
            intensity=state.effective_intensity,
        )

    def _signature_similarity(
        self,
        current: ExpressionSignature,
        recent: ExpressionSignature,
    ) -> float:
        current_units = set(current.unit_ids)
        recent_units = set(recent.unit_ids)
        unit_similarity = len(current_units & recent_units) / max(
            len(current_units | recent_units), 1
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

        tag_similarity = len(current.semantic_tags & recent.semantic_tags) / max(
            len(current.semantic_tags | recent.semantic_tags),
            1,
        )
        emotion_similarity = 1.0 if current.emotion is recent.emotion else 0.0
        intensity_similarity = max(0.0, 1.0 - abs(current.intensity - recent.intensity))
        return (
            unit_similarity * 0.35
            + target_similarity * 0.25
            + tag_similarity * 0.15
            + emotion_similarity * 0.15
            + intensity_similarity * 0.10
        )

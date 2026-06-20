"""表情解算器：实现完整 AU 选择算法"""

from __future__ import annotations

import random

from livestudio.services.semantic_actions.models import (
    FacialRegion,
    clamp_semantic_value,
)

from .history import ExpressionHistory
from .models import (
    BindingRule,
    BonusRule,
    EmotionKind,
    ExpressionRequest,
    ExpressionRule,
    ExpressionSignature,
    ExpressionUnit,
    MutualExclusionRule,
    NativeExpressionTrigger,
    PenaltyRule,
    ResolvedSemanticTarget,
    ScoredExpressionUnit,
    SelectedExpression,
    SemanticExpressionUnit,
)


class ExpressionSolver:
    def __init__(
        self,
        units: list[ExpressionUnit],
        rules: list[ExpressionRule],
        history: ExpressionHistory,
        top_candidates: int = 14,
    ) -> None:
        self._units = units
        self._rules = rules
        self._history = history
        self._top_candidates = top_candidates

    @property
    def history(self) -> ExpressionHistory:
        return self._history

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def solve(self, request: ExpressionRequest) -> SelectedExpression:
        """执行完整选择算法并更新历史"""
        result = self._run(request)
        self._history.record(ExpressionSignature(unit_ids=frozenset(u.id for u in result.units), emotion=request.emotion))
        return result

    def preview(self, request: ExpressionRequest) -> SelectedExpression:
        """预览模式：不更新历史"""
        return self._run(request)

    # ── 内部实现 ──────────────────────────────────────────────────────────────

    def _run(self, request: ExpressionRequest) -> SelectedExpression:
        recent_ids = self._history.recent_unit_ids
        candidates = self._score_units(request, recent_ids)
        if not candidates:
            return _empty(request.emotion)

        ranked = sorted(candidates, key=lambda s: self._rank(s, request), reverse=True)
        combo = self._build_combo(ranked, request)
        return self._make_result(combo, request)

    def _score_units(self, request: ExpressionRequest, recent_ids: frozenset[str]) -> list[ScoredExpressionUnit]:
        result: list[ScoredExpressionUnit] = []
        for unit in self._units:
            correlation = unit.emotions.get(request.emotion, 0.0)
            if correlation <= 0.0 or correlation < unit.activation_threshold:
                continue
            novelty = 0.35 if unit.id in recent_ids else 1.0
            score = correlation * 0.80 + novelty * 0.20
            if score < request.min_au_score:
                continue
            result.append(ScoredExpressionUnit(unit=unit, score=score, correlation=correlation))
        result.sort(key=lambda s: s.score, reverse=True)
        return result[: self._top_candidates]

    def _rank(self, scored: ScoredExpressionUnit, request: ExpressionRequest) -> float:
        if request.randomness <= 0.0:
            return scored.score
        return scored.score + random.uniform(-1.0, 1.0) * request.randomness * request.diversity * 0.30

    def _should_select(self, scored: ScoredExpressionUnit, request: ExpressionRequest) -> bool:
        if scored.score >= request.core_score or scored.correlation >= 0.80 or request.randomness <= 0.0:
            return True
        p = min(
            1.0,
            max(0.05, scored.score) * (0.55 + request.diversity * 0.55) + scored.correlation * 0.20,
        )
        return random.random() <= p

    def _build_combo(self, ranked: list[ScoredExpressionUnit], request: ExpressionRequest) -> list[ScoredExpressionUnit]:
        combo: list[ScoredExpressionUnit] = []
        occupied_actions: set[str] = set()

        for candidate in ranked:
            if len(combo) >= request.max_units:
                break
            if not self._should_select(candidate, request):
                continue

            # 互斥冲突检查（显式规则 + 隐式 action 冲突）
            conflict = self._find_conflict(candidate, combo, occupied_actions, request.emotion)
            if conflict == "discard":
                continue
            if isinstance(conflict, ScoredExpressionUnit):
                combo.remove(conflict)
                if isinstance(conflict.unit, SemanticExpressionUnit):
                    occupied_actions -= {t.action for t in conflict.unit.targets}

            # BINDING 合法性检查（强制绑定）
            new_ids = {s.unit.id for s in combo} | {candidate.unit.id}
            if not self._binding_legal(new_ids, request.emotion):
                continue

            combo.append(candidate)
            if isinstance(candidate.unit, SemanticExpressionUnit):
                occupied_actions.update(t.action for t in candidate.unit.targets)

        return combo

    def _find_conflict(
        self,
        candidate: ScoredExpressionUnit,
        combo: list[ScoredExpressionUnit],
        occupied_actions: set[str],
        emotion: object,
    ) -> ScoredExpressionUnit | str | None:
        """返回 None（无冲突）、被替换的 ScoredExpressionUnit、或 'discard'"""
        # 1. 显式互斥规则
        for rule in self._rules:
            if not isinstance(rule, MutualExclusionRule):
                continue
            if rule.emotions and emotion not in rule.emotions:
                continue
            if candidate.unit.id not in rule.unit_ids:
                continue
            for existing in combo:
                if existing.unit.id in rule.unit_ids:
                    return self._resolve_conflict(candidate, existing)

        # 2. 隐式 action 冲突（仅 SemanticExpressionUnit）
        if isinstance(candidate.unit, SemanticExpressionUnit):
            candidate_actions = {t.action for t in candidate.unit.targets}
            if candidate_actions & occupied_actions:
                for existing in combo:
                    if not isinstance(existing.unit, SemanticExpressionUnit):
                        continue
                    if {t.action for t in existing.unit.targets} & candidate_actions:
                        return self._resolve_conflict(candidate, existing)

        return None

    def _resolve_conflict(self, candidate: ScoredExpressionUnit, existing: ScoredExpressionUnit) -> ScoredExpressionUnit | str:
        if candidate.score > existing.score + 0.03:
            return existing  # 替换 existing
        return "discard"

    def _binding_legal(self, combo_ids: set[str], emotion: object) -> bool:
        for rule in self._rules:
            if not isinstance(rule, BindingRule):
                continue
            if rule.emotions and emotion not in rule.emotions:
                continue
            if rule.penalty != float("inf"):
                continue  # 软惩罚在 combo_score 里处理，此处只检查强制绑定
            present = combo_ids & rule.unit_ids
            if present and present != rule.unit_ids:
                return False
        return True

    def _combo_score(self, combo: list[ScoredExpressionUnit], request: ExpressionRequest) -> float:
        combo_ids = {s.unit.id for s in combo}
        covered: set[FacialRegion] = set()
        for s in combo:
            covered.update(s.unit.regions)

        base = sum(s.score for s in combo)
        coverage = min(1.0, len(covered) / 4.0) * 0.14
        size_penalty = max(0, len(combo) - 1) * 0.06
        rule_score = self._rule_score(combo_ids, request.emotion)
        hist_penalty = self._history.penalty(
            ExpressionSignature(unit_ids=frozenset(combo_ids), emotion=request.emotion),
            request.history_avoidance,
        )
        return base + coverage - size_penalty + rule_score - hist_penalty

    def _rule_score(self, combo_ids: set[str], emotion: object) -> float:
        score = 0.0
        for rule in self._rules:
            if rule.emotions and emotion not in rule.emotions:
                continue
            if isinstance(rule, BonusRule) and rule.unit_ids <= combo_ids:
                score += rule.value
            elif isinstance(rule, PenaltyRule) and rule.unit_ids <= combo_ids:
                score -= rule.value
            elif isinstance(rule, BindingRule) and rule.penalty != float("inf"):
                present = combo_ids & rule.unit_ids
                if present and present != rule.unit_ids:
                    score -= rule.penalty
        return score

    def _make_result(self, combo: list[ScoredExpressionUnit], request: ExpressionRequest) -> SelectedExpression:
        semantic_targets: list[ResolvedSemanticTarget] = []
        native_triggers: list[NativeExpressionTrigger] = []
        units_by_region: dict[FacialRegion, list[ExpressionUnit]] = {}
        units: list[ExpressionUnit] = []

        for scored in combo:
            unit = scored.unit
            units.append(unit)
            for region in unit.regions:
                units_by_region.setdefault(region, []).append(unit)

            if isinstance(unit, SemanticExpressionUnit):
                for target in unit.targets:
                    value = random.uniform(target.min_value, target.max_value)
                    value = clamp_semantic_value(target.action, value)
                    semantic_targets.append(ResolvedSemanticTarget(action=target.action, value=value, easing=unit.easing))
            else:
                native_triggers.append(NativeExpressionTrigger(platform=unit.platform, native_ref=unit.native_ref))

        total_score = self._combo_score(combo, request)
        return SelectedExpression(
            units=units,
            emotion=request.emotion,
            score=total_score,
            semantic_targets=semantic_targets,
            native_triggers=native_triggers,
            units_by_region=units_by_region,
        )


def _empty(emotion: EmotionKind) -> SelectedExpression:
    return SelectedExpression(
        units=[],
        emotion=emotion,
        score=0.0,
        semantic_targets=[],
        native_triggers=[],
        units_by_region={},
    )

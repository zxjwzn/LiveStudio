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
        *,
        rng: random.Random | None = None,
    ) -> None:
        self._units = units
        self._rules = rules
        self._history = history
        self._top_candidates = top_candidates
        # 注入随机源，便于测试用固定种子获得确定性结果；默认用独立实例不污染全局 random
        self._rng = rng or random.Random()

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
            result.append(ScoredExpressionUnit(unit=unit, score=score, correlation=correlation))
        result.sort(key=lambda s: s.score, reverse=True)
        return result[: self._top_candidates]

    def _rank(self, scored: ScoredExpressionUnit, request: ExpressionRequest) -> float:
        if request.randomness <= 0.0:
            return scored.score
        return scored.score + self._rng.uniform(-1.0, 1.0) * request.randomness * request.diversity * 0.30

    def _should_select(self, scored: ScoredExpressionUnit, request: ExpressionRequest) -> bool:
        if scored.score >= request.core_score or scored.correlation >= 0.80 or request.randomness <= 0.0:
            return True
        p = min(
            1.0,
            max(0.05, scored.score) * (0.55 + request.diversity * 0.55) + scored.correlation * 0.20,
        )
        return self._rng.random() <= p

    def _build_combo(self, ranked: list[ScoredExpressionUnit], request: ExpressionRequest) -> list[ScoredExpressionUnit]:
        combo: list[ScoredExpressionUnit] = []
        occupied_actions: set[str] = set()
        unmet = 1.0  # 情绪「未满足残量」，noisy-OR 累计：选入越多越趋近 0

        for candidate in ranked:
            if len(combo) >= request.max_units:
                break
            if not self._should_select(candidate, request):
                continue

            # 互斥冲突检查（显式规则 + 隐式 action 冲突）。
            # 一个候选可能同时与多个已入选单元冲突（多 target 时尤甚），必须全部收集后统一裁决，
            # 否则只顶替其中一个会让候选与剩余冲突单元共占同一 action，留下非法组合。
            conflicts = self._find_conflicts(candidate, combo, request.emotion)
            if conflicts:
                strongest = max(c.score for c in conflicts)
                if candidate.score <= strongest + 0.03:
                    continue  # 不足以顶替最强冲突者，丢弃候选
                for victim in conflicts:
                    combo.remove(victim)
                    if isinstance(victim.unit, SemanticExpressionUnit):
                        occupied_actions -= {t.action for t in victim.unit.targets}

            # BINDING 合法性检查（强制绑定）
            new_ids = {s.unit.id for s in combo} | {candidate.unit.id}
            if not self._binding_legal(new_ids, request.emotion):
                continue

            combo.append(candidate)
            if isinstance(candidate.unit, SemanticExpressionUnit):
                occupied_actions.update(t.action for t in candidate.unit.targets)

            # 情绪饱和提前收手（多样性来源）：累计满足度足够后，按 (1 - diversity) 概率停手，
            # 让「单个完整表情」与「多 AU 叠加」都能出现。randomness<=0 时保持确定性，不提前停。
            unmet *= 1.0 - max(0.0, min(1.0, candidate.correlation))
            if (
                request.randomness > 0.0
                and 1.0 - unmet >= 0.90
                and self._rng.random() > request.diversity
            ):
                break

        return combo

    def _find_conflicts(
        self,
        candidate: ScoredExpressionUnit,
        combo: list[ScoredExpressionUnit],
        emotion: EmotionKind,
    ) -> list[ScoredExpressionUnit]:
        """收集 combo 中所有与 candidate 冲突的已入选单元（显式互斥规则 + 隐式 action 冲突）。

        与旧版「命中第一个就返回」不同，这里返回全部冲突者：多 target 候选可能同时与
        几个已入选单元各冲突一个 action，调用方需要看到完整冲突集才能正确裁决与回收。
        """
        conflicts: list[ScoredExpressionUnit] = []

        candidate_actions: set[str] = set()
        if isinstance(candidate.unit, SemanticExpressionUnit):
            candidate_actions = {t.action for t in candidate.unit.targets}

        # 当前情绪下生效、且包含 candidate 的显式互斥规则的并集
        mutex_ids: set[str] = set()
        for rule in self._rules:
            if not isinstance(rule, MutualExclusionRule):
                continue
            if rule.emotions and emotion not in rule.emotions:
                continue
            if candidate.unit.id in rule.unit_ids:
                mutex_ids |= rule.unit_ids

        for existing in combo:
            # 1. 显式互斥
            if existing.unit.id in mutex_ids:
                conflicts.append(existing)
                continue
            # 2. 隐式 action 冲突（仅两端都是 SemanticExpressionUnit 时）
            if (
                candidate_actions
                and isinstance(existing.unit, SemanticExpressionUnit)
                and {t.action for t in existing.unit.targets} & candidate_actions
            ):
                conflicts.append(existing)

        return conflicts

    @staticmethod
    def _binding_violated(rule: BindingRule, combo_ids: set[str]) -> bool:
        """绑定规则是否被违反：组合命中了规则的部分单元但未覆盖全部（部分绑定即违反）。"""

        present = combo_ids & rule.unit_ids
        return bool(present) and present != rule.unit_ids

    def _binding_legal(self, combo_ids: set[str], emotion: EmotionKind) -> bool:
        for rule in self._rules:
            if not isinstance(rule, BindingRule):
                continue
            if rule.emotions and emotion not in rule.emotions:
                continue
            if rule.penalty != float("inf"):
                continue  # 软惩罚在 combo_score 里处理，此处只检查强制绑定
            if self._binding_violated(rule, combo_ids):
                return False
        return True

    def _combo_score(self, combo: list[ScoredExpressionUnit], request: ExpressionRequest) -> float:
        combo_ids = {s.unit.id for s in combo}
        covered: set[FacialRegion] = set()
        for s in combo:
            covered.update(s.unit.regions)

        # 情绪饱和度（noisy-OR）：值域恒为 [0,1]，单个高相关 AU 即可逼近 1，
        # 避免 sum 让「AU 数量」碾压「单个完整表情」——单一区域表情也能拿到接近满额的基础分。
        unmet = 1.0
        for s in combo:
            unmet *= 1.0 - max(0.0, min(1.0, s.correlation))
        fulfillment = 1.0 - unmet

        # 多区域覆盖只作小额「锦上添花」，分母随 FacialRegion 成员数自适应（不再写死 4）。
        variety = min(1.0, len(covered) / len(FacialRegion)) * 0.10
        size_penalty = max(0, len(combo) - 1) * 0.04
        rule_score = self._rule_score(combo_ids, request.emotion)
        hist_penalty = self._history.penalty(
            ExpressionSignature(unit_ids=frozenset(combo_ids), emotion=request.emotion),
            request.history_avoidance,
        )
        return fulfillment + variety - size_penalty + rule_score - hist_penalty

    def _rule_score(self, combo_ids: set[str], emotion: EmotionKind) -> float:
        score = 0.0
        for rule in self._rules:
            if rule.emotions and emotion not in rule.emotions:
                continue
            if isinstance(rule, BonusRule) and rule.unit_ids <= combo_ids:
                score += rule.value
            elif isinstance(rule, PenaltyRule) and rule.unit_ids <= combo_ids:
                score -= rule.value
            elif (
                isinstance(rule, BindingRule)
                and rule.penalty != float("inf")
                and self._binding_violated(rule, combo_ids)
            ):
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
                    value = self._rng.uniform(target.min_value, target.max_value)
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

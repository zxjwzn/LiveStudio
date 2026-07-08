"""表情解算器：实现完整 AU 选择算法（v3 典型度门控）"""

from __future__ import annotations

import math
import random

from livestudio.services.semantic_actions.models import (
    FacialRegion,
    clamp_semantic_value,
    neutral_value,
    semantic_actions_overlap,
)
from livestudio.utils.log import logger

from .history import ExpressionHistory
from .models import (
    BonusRule,
    EmotionKind,
    ExpressionRequest,
    ExpressionRule,
    ExpressionSignature,
    ExpressionUnit,
    MutualExclusionRule,
    NativeExpressionTrigger,
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
        typicality_floor: float = 0.30,
        typicality_power: float = 0.5,
        rng: random.Random | None = None,
    ) -> None:
        self._units = units
        self._rules = rules
        self._history = history
        self._top_candidates = top_candidates
        # 典型度门控参数（v3）：τ 硬门（客串门槛）/ α 软折扣指数
        self._typicality_floor = typicality_floor
        self._typicality_power = typicality_power
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
        logger.debug("AU 解算历史已记录: emotion={}, signature={}", request.emotion, [unit.id for unit in result.units])
        return result

    def preview(self, request: ExpressionRequest) -> SelectedExpression:
        """预览模式：不更新历史"""
        return self._run(request)

    # ── 内部实现 ──────────────────────────────────────────────────────────────

    def _run(self, request: ExpressionRequest) -> SelectedExpression:
        recent_ids = self._history.recent_unit_ids
        logger.debug(
            "AU 解算开始: emotion={}, intensity={}, max_units={}, core_score={}, randomness={}, diversity={}, history_avoidance={}, typicality_floor={}, typicality_power={}, recent={}",
            request.emotion,
            request.intensity,
            request.max_units,
            request.core_score,
            request.randomness,
            request.diversity,
            request.history_avoidance,
            self._typicality_floor,
            self._typicality_power,
            sorted(recent_ids),
        )
        candidates = self._score_units(request, recent_ids)
        if not candidates:
            logger.debug("AU 解算无候选: emotion={}", request.emotion)
            return _empty(request.emotion)

        ranked_pairs = [(candidate, self._rank(candidate, request)) for candidate in candidates]
        logger.debug("AU 候选评分: {}", [_scored_unit_log(candidate) for candidate in candidates])
        logger.debug(
            "AU 排序评分: {}",
            [
                {
                    "id": candidate.unit.id,
                    "rank": round(rank, 4),
                    "score": round(candidate.score, 4),
                    "correlation": round(candidate.correlation, 4),
                    "typicality": round(candidate.typicality, 4),
                }
                for candidate, rank in ranked_pairs
            ],
        )
        ranked = [candidate for candidate, _ in sorted(ranked_pairs, key=lambda pair: pair[1], reverse=True)]
        combo = self._build_combo(ranked, request)
        result = self._make_result(combo, request)
        logger.debug(
            "AU 解算完成: emotion={}, units={}, score={}, semantic_targets={}, native_triggers={}",
            result.emotion,
            [unit.id for unit in result.units],
            round(result.score, 4),
            [_semantic_target_log(target) for target in result.semantic_targets],
            [trigger.native_ref for trigger in result.native_triggers],
        )
        return result

    def _resolve_correlation(self, unit: ExpressionUnit, emotion: EmotionKind) -> tuple[float, bool]:
        """解析 AU 在当前情绪下的相关性及来源。

        显式打分（含显式 <=0 = 禁用）优先；缺失时用 baseline 百搭分兜底。
        返回 (correlation, via_baseline)。
        """
        if emotion in unit.emotions:
            return unit.emotions[emotion], False
        return unit.baseline, (unit.baseline > 0.0)

    def _peak_correlation(self, unit: ExpressionUnit) -> float:
        """AU 打分行峰值，用于典型度分母。"""
        return max(max(unit.emotions.values(), default=0.0), unit.baseline)

    def _score_units(self, request: ExpressionRequest, recent_ids: frozenset[str]) -> list[ScoredExpressionUnit]:
        """单体打分 + 典型度硬门过滤（v3）。

        硬门在候选池阶段裁决——即使 randomness=0 也生效，
        因为这是「身份不合」的结构性拒绝，不是随机选择性降频。
        """
        result: list[ScoredExpressionUnit] = []
        for unit in self._units:
            correlation, via_baseline = self._resolve_correlation(unit, request.emotion)
            if correlation <= 0.0:
                continue
            # 典型度 = 当前格分 / 打分行峰值：识别「本职还是客串」
            peak = self._peak_correlation(unit)
            typicality = correlation / peak
            if typicality < self._typicality_floor:
                logger.debug(
                    "AU 候选剔除: id={}, 原因=典型度不足, typicality={}, correlation={}, peak={}",
                    unit.id,
                    round(typicality, 4),
                    round(correlation, 4),
                    round(peak, 4),
                )
                continue
            novelty = 0.35 if unit.id in recent_ids else 1.0
            score = correlation * 0.80 + novelty * 0.20
            result.append(
                ScoredExpressionUnit(
                    unit=unit,
                    score=score,
                    correlation=correlation,
                    typicality=typicality,
                    via_baseline=via_baseline,
                )
            )
        result.sort(key=lambda s: s.score, reverse=True)
        return result[: self._top_candidates]

    def _rank(self, scored: ScoredExpressionUnit, request: ExpressionRequest) -> float:
        if request.randomness <= 0.0:
            return scored.score
        return scored.score + self._rng.uniform(-1.0, 1.0) * request.randomness * request.diversity * 0.30

    def _selection_decision(self, scored: ScoredExpressionUnit, request: ExpressionRequest) -> tuple[bool, float]:
        """概率门 + 典型度软折扣（v3）。

        randomness<=0 时保持确定性直通——典型度硬门已在打分阶段生效，
        软折扣依赖掷骰，确定性路径跳过。
        """
        if request.randomness <= 0.0:
            return True, 1.0
        if scored.score >= request.core_score or scored.correlation >= 0.80:
            base = 1.0
        else:
            base = min(
                1.0,
                max(0.05, scored.score) * (0.55 + request.diversity * 0.55) + scored.correlation * 0.20,
            )
        # 客串折扣：本职 AU（typicality=1）无影响，客串按 typ^α 降频
        p = base * scored.typicality**self._typicality_power
        return self._rng.random() <= p, p

    def _build_combo(self, ranked: list[ScoredExpressionUnit], request: ExpressionRequest) -> list[ScoredExpressionUnit]:
        combo: list[ScoredExpressionUnit] = []
        occupied_actions: set[str] = set()
        unmet = 1.0  # 情绪「未满足残量」，noisy-OR 累计：选入越多越趋近 0

        for candidate in ranked:
            if len(combo) >= request.max_units:
                logger.debug(
                    "AU 选择停止: 原因=max_units, max_units={}, combo={}",
                    request.max_units,
                    [selected.unit.id for selected in combo],
                )
                break
            # ── v3：百搭候选不得当锚 ──
            if candidate.via_baseline and not combo:
                logger.debug(
                    "AU 候选跳过: id={}, 原因=百搭分不当锚",
                    candidate.unit.id,
                )
                continue
            accepted_by_probability, probability = self._selection_decision(candidate, request)
            if not accepted_by_probability:
                logger.debug(
                    "AU 候选跳过: id={}, 原因=概率未命中, probability={}, score={}, correlation={}, typicality={}",
                    candidate.unit.id,
                    round(probability, 4),
                    round(candidate.score, 4),
                    round(candidate.correlation, 4),
                    round(candidate.typicality, 4),
                )
                continue

            # 互斥冲突检查（显式规则 + 隐式 action 冲突）。
            conflicts = self._find_conflicts(candidate, combo, request.emotion)
            if conflicts:
                # ── v3：百搭候选不参与顶替 ──
                if candidate.via_baseline:
                    logger.debug(
                        "AU 候选跳过: id={}, 原因=百搭候选不参与顶替, conflicts={}",
                        candidate.unit.id,
                        [conflict.unit.id for conflict in conflicts],
                    )
                    continue
                strongest = max(c.score for c in conflicts)
                strongest_weight = max(_unit_control_weight(c.unit) for c in conflicts)
                replace_margin = 0.03 + max(0.0, strongest_weight - _unit_control_weight(candidate.unit)) * 0.08
                if candidate.score <= strongest + replace_margin:
                    logger.debug(
                        "AU 候选跳过: id={}, 原因=互斥冲突, conflicts={}, candidate_score={}, strongest_conflict={}",
                        candidate.unit.id,
                        [conflict.unit.id for conflict in conflicts],
                        round(candidate.score, 4),
                        round(strongest, 4),
                    )
                    continue  # 不足以顶替最强冲突者，丢弃候选
                logger.debug(
                    "AU 冲突替换: candidate={}, victims={}",
                    candidate.unit.id,
                    [victim.unit.id for victim in conflicts],
                )
                for victim in conflicts:
                    combo.remove(victim)
                    if isinstance(victim.unit, SemanticExpressionUnit):
                        occupied_actions -= {t.action for t in victim.unit.targets}

            combo.append(candidate)
            if isinstance(candidate.unit, SemanticExpressionUnit):
                occupied_actions.update(t.action for t in candidate.unit.targets)
            logger.debug(
                "AU 候选选中: id={}, probability={}, typicality={}, combo={}, occupied_actions={}",
                candidate.unit.id,
                round(probability, 4),
                round(candidate.typicality, 4),
                [selected.unit.id for selected in combo],
                sorted(occupied_actions),
            )

            # 情绪饱和提前收手（多样性来源）
            unmet *= 1.0 - max(0.0, min(1.0, candidate.correlation))
            covered_regions = {region for selected in combo for region in selected.unit.regions}
            if (
                request.randomness > 0.0
                and 1.0 - unmet >= 0.90
                and len(covered_regions) >= 2
                and self._rng.random() > request.diversity
            ):
                logger.debug(
                    "AU 选择停止: 原因=情绪满足度已达阈值, fulfillment={}, diversity={}, combo={}",
                    round(1.0 - unmet, 4),
                    request.diversity,
                    [selected.unit.id for selected in combo],
                )
                break

        logger.debug("AU 组合结果: {}", [_scored_unit_log(selected) for selected in combo])
        return combo

    def _find_conflicts(
        self,
        candidate: ScoredExpressionUnit,
        combo: list[ScoredExpressionUnit],
        emotion: EmotionKind,
    ) -> list[ScoredExpressionUnit]:
        """收集 combo 中所有与 candidate 冲突的已入选单元（显式互斥规则 + 隐式 action 冲突）。"""
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
                and _actions_overlap(candidate_actions, {t.action for t in existing.unit.targets})
            ):
                conflicts.append(existing)

        return conflicts

    def _combo_score(self, combo: list[ScoredExpressionUnit], request: ExpressionRequest) -> float:
        combo_ids = {s.unit.id for s in combo}
        covered: set[FacialRegion] = set()
        for s in combo:
            covered.update(s.unit.regions)

        # 情绪饱和度（noisy-OR）
        unmet = 1.0
        for s in combo:
            unmet *= 1.0 - max(0.0, min(1.0, s.correlation))
        fulfillment = 1.0 - unmet

        # 多区域覆盖用对数曲线；v3：乘以成员典型度均值，防止「靠客串凑跨区域」骗分
        typ_mean = sum(s.typicality for s in combo) / len(combo) if combo else 1.0
        region_steps = max(0, len(covered) - 1)
        variety = math.log1p(region_steps) / math.log(len(FacialRegion)) * 0.22 * typ_mean if region_steps else 0.0
        size_penalty = max(0, len(combo) - 1) * 0.04
        rule_score = self._rule_score(combo_ids, request.emotion)
        hist_penalty = self._history.penalty(
            ExpressionSignature(unit_ids=frozenset(combo_ids), emotion=request.emotion),
            request.history_avoidance,
        )
        total = fulfillment + variety - size_penalty + rule_score - hist_penalty
        logger.debug(
            "AU 组合评分: units={}, fulfillment={}, variety={}, size_penalty={}, rule_score={}, history_penalty={}, typ_mean={}, total={}",
            sorted(combo_ids),
            round(fulfillment, 4),
            round(variety, 4),
            round(size_penalty, 4),
            round(rule_score, 4),
            round(hist_penalty, 4),
            round(typ_mean, 4),
            round(total, 4),
        )
        return total

    def _rule_score(self, combo_ids: set[str], emotion: EmotionKind) -> float:
        score = 0.0
        for rule in self._rules:
            if rule.emotions and emotion not in rule.emotions:
                continue
            if isinstance(rule, BonusRule) and rule.unit_ids <= combo_ids:
                score += rule.value
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
                    sampled_value = self._rng.uniform(target.min_value, target.max_value)
                    neutral = neutral_value(target.action)
                    value = neutral + (sampled_value - neutral) * request.intensity
                    value = clamp_semantic_value(target.action, value)
                    logger.debug(
                        "AU 目标生成: unit={}, action={}, range=[{}, {}], sampled={}, neutral={}, intensity={}, value={}, easing={}",
                        unit.id,
                        target.action,
                        target.min_value,
                        target.max_value,
                        round(sampled_value, 4),
                        round(neutral, 4),
                        request.intensity,
                        round(value, 4),
                        unit.easing,
                    )
                    semantic_targets.append(ResolvedSemanticTarget(action=target.action, value=value, easing=unit.easing))
            else:
                logger.debug("AU 原生触发生成: unit={}, platform={}, native_ref={}", unit.id, unit.platform, unit.native_ref)
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


def _scored_unit_log(scored: ScoredExpressionUnit) -> dict[str, object]:
    unit = scored.unit
    item: dict[str, object] = {
        "id": unit.id,
        "type": "semantic" if isinstance(unit, SemanticExpressionUnit) else "native",
        "score": round(scored.score, 4),
        "correlation": round(scored.correlation, 4),
        "typicality": round(scored.typicality, 4),
        "via_baseline": scored.via_baseline,
        "regions": sorted(region.value for region in unit.regions),
    }
    if isinstance(unit, SemanticExpressionUnit):
        item["actions"] = [target.action for target in unit.targets]
    else:
        item["native_ref"] = unit.native_ref
    return item


def _semantic_target_log(target: ResolvedSemanticTarget) -> dict[str, object]:
    return {"action": target.action, "value": round(target.value, 4), "easing": target.easing}


def _actions_overlap(left: set[str], right: set[str]) -> bool:
    return any(semantic_actions_overlap(left_action, right_action) for left_action in left for right_action in right)


def _unit_control_weight(unit: ExpressionUnit) -> int:
    if isinstance(unit, SemanticExpressionUnit):
        return len(unit.targets)
    return max(1, len(unit.regions))

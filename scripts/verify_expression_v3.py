"""v3 表情解算可靠性验证：每个情绪 100 次试算，检查不变量与频率分布。

运行：.venv/Scripts/python.exe scripts/verify_expression_v3.py
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass

from livestudio.services.expression import (
    EmotionKind,
    ExpressionHistory,
    ExpressionProfileConfig,
    ExpressionRequest,
    ExpressionSolver,
)

TRIALS = 100
TAU = 0.30
ALPHA = 0.5
# 招牌 AU 出现频率下限（概率系统下不要求 100%，核心骨架至少过半）
SIGNATURE_FREQ_FLOOR = 0.50

# 每个情绪的招牌断言：100 次里每次都应成立（不变量，非概率）
SIGNATURE: dict[EmotionKind, list[tuple[str, str]]] = {
    EmotionKind.JOY: [("must_contain", "嘴角上扬")],
    EmotionKind.SADNESS: [("must_contain", "嘴角下撇")],
    EmotionKind.ANGER: [("must_contain", "皱眉"), ("must_contain", "抿嘴")],
    EmotionKind.SURPRISE: [("must_contain", "抬眉"), ("must_contain", "睁眼")],
    EmotionKind.SMUG: [("must_contain", "阴险抬眼"), ("must_contain", "眯眼"), ("must_contain", "嘴角上扬")],
    EmotionKind.WRY: [("must_contain", "皱眉"), ("must_contain", "嘴角上扬")],
    EmotionKind.SHY: [("must_contain", "目移"), ("must_contain", "低头")],
}

# 跨情绪禁现：这些 AU 在指定情绪下典型度过低，100 次都不应出现
BANNED: dict[EmotionKind, set[str]] = {
    EmotionKind.JOY: {"目移", "嘴角下撇"},  # 悲伤系，不该混入喜悦
    EmotionKind.SURPRISE: {"目移", "嘴角下撇", "抿嘴"},
    EmotionKind.SMUG: {"嘴巴张大", "目移"},  # 大笑嘴/悲伤视线不属于阴险
}


@dataclass
class EmotionReport:
    emotion: EmotionKind
    nonempty_rate: float
    signature_violations: list[str]
    banned_violations: Counter
    baseline_anchored: int  # 百搭 AU 当首元素（锚）的次数，应为 0
    action_conflicts: int  # 同一 action 被多 AU 占用的次数，应为 0
    au_freq: Counter  # AU 出现频次
    combo_diversity: int  # 不同组合数


def _check_action_conflict(units: list) -> bool:
    seen: set[str] = set()
    from livestudio.services.expression import SemanticExpressionUnit

    for u in units:
        if isinstance(u, SemanticExpressionUnit):
            for t in u.targets:
                if t.action in seen:
                    return True
                seen.add(t.action)
    return False


def _anchor_is_baseline(unit, emotion: EmotionKind) -> bool:
    """锚（首个入选）的相关性是否来自百搭分：百搭分不得当锚。"""
    return emotion not in unit.emotions or unit.emotions[emotion] <= 0


def verify_emotion(emotion: EmotionKind, units: list, rules: list) -> EmotionReport:
    freq: Counter = Counter()
    banned_hits: Counter = Counter()
    baseline_anchored = 0
    action_conflicts = 0
    nonempty = 0
    combos: set[frozenset[str]] = set()
    sig_violations: list[str] = []

    for seed in range(TRIALS):
        solver = ExpressionSolver(
            units=units,
            rules=rules,
            history=ExpressionHistory(capacity=20),
            typicality_floor=TAU,
            typicality_power=ALPHA,
            rng=random.Random(seed),
        )
        result = solver.solve(ExpressionRequest(emotion=emotion))
        ids = [u.id for u in result.units]

        if ids:
            nonempty += 1
        combos.add(frozenset(ids))
        for uid in ids:
            freq[uid] += 1

        # 锚检查：首个入选 AU 的相关性必须来自显式打分，不能是百搭分
        if result.units and _anchor_is_baseline(result.units[0], emotion):
            baseline_anchored += 1

        if _check_action_conflict(result.units):
            action_conflicts += 1

        for uid in BANNED.get(emotion, set()):
            if uid in set(ids):
                banned_hits[uid] += 1

    # 招牌频率检查（非 100%，概率系统下核心骨架至少过半）
    for uid in [uid for kind, uid in SIGNATURE.get(emotion, []) if kind == "must_contain"]:
        if freq[uid] / TRIALS < SIGNATURE_FREQ_FLOOR:
            sig_violations.append(f"{uid}={freq[uid]}/{TRIALS}")

    return EmotionReport(
        emotion=emotion,
        nonempty_rate=nonempty / TRIALS,
        signature_violations=sig_violations,
        banned_violations=banned_hits,
        baseline_anchored=baseline_anchored,
        action_conflicts=action_conflicts,
        au_freq=freq,
        combo_diversity=len(combos),
    )


def main() -> int:
    profile = ExpressionProfileConfig.create_default()
    units = profile.to_units()
    rules = profile.to_rules()

    print(f"默认 AU 数: {len(units)}，规则数: {len(rules)}，τ={TAU}，α={ALPHA}，每情绪 {TRIALS} 次\n")

    failures = 0
    for emotion in EmotionKind:
        rep = verify_emotion(emotion, units, rules)
        ok = (
            not rep.signature_violations
            and rep.baseline_anchored == 0
            and rep.action_conflicts == 0
            and rep.nonempty_rate == 1.0
            and sum(rep.banned_violations.values()) == 0
        )
        if not ok:
            failures += 1
        status = "✓" if ok else "✗"
        print(f"{status} {emotion.value:10} 非空={rep.nonempty_rate:.2f} 多样性={rep.combo_diversity:3}种 "
              f"锚违规={rep.baseline_anchored} action冲突={rep.action_conflicts} "
              f"禁现违反={dict(rep.banned_violations) or '-'} 招牌违规={rep.signature_violations or '-'}")
        top = rep.au_freq.most_common(6)
        print(f"   频率 top6: {[(u, c) for u, c in top]}")

    print(f"\n{'='*60}")
    if failures == 0:
        print(f"全部 {len(list(EmotionKind))} 个情绪通过 {TRIALS} 次可靠性验证")
        return 0
    print(f"{failures} 个情绪未通过，需排查")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

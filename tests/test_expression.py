from __future__ import annotations

import random

import pytest
from pydantic import ValidationError

from livestudio.services.expression.config import ExpressionProfileConfig
from livestudio.services.expression.history import ExpressionHistory
from livestudio.services.expression.models import (
    BonusRule,
    EmotionKind,
    ExpressionRequest,
    ExpressionSignature,
    ExpressionTarget,
    MutualExclusionRule,
    NativeExpressionUnit,
    SemanticExpressionUnit,
)
from livestudio.services.expression.solver import ExpressionSolver
from livestudio.services.semantic_actions.models import FacialRegion, SemanticAction, neutral_value

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _joy_unit(uid: str, correlation: float = 0.80) -> SemanticExpressionUnit:
    return SemanticExpressionUnit(
        id=uid,
        targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.5, max_value=0.9)],
        emotions={EmotionKind.JOY: correlation},
    )


def _anger_brow_unit() -> SemanticExpressionUnit:
    return SemanticExpressionUnit(
        id="皱眉",
        targets=[ExpressionTarget(action=SemanticAction.BROW_HEIGHT, min_value=0.0, max_value=0.2)],
        emotions={EmotionKind.ANGER: 0.89},
    )


def _native_joy_unit() -> NativeExpressionUnit:
    return NativeExpressionUnit(
        id="开心特效",
        platform="vtubestudio",
        native_ref="2脸红",
        regions=frozenset([FacialRegion.EYE]),
        emotions={EmotionKind.JOY: 0.85},
    )


def _make_solver(*units: SemanticExpressionUnit | NativeExpressionUnit, rules: list | None = None) -> ExpressionSolver:
    return ExpressionSolver(units=list(units), rules=rules or [], history=ExpressionHistory(capacity=10))


# ── ExpressionTarget ──────────────────────────────────────────────────────────


def test_target_fields() -> None:
    t = ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.1, max_value=0.9)
    assert t.action == SemanticAction.MOUTH_SMILE
    assert t.min_value == 0.1
    assert t.max_value == 0.9


# ── SemanticExpressionUnit ────────────────────────────────────────────────────


def test_semantic_unit_regions_derived() -> None:
    unit = _anger_brow_unit()
    assert FacialRegion.BROW in unit.regions


def test_semantic_unit_unrelated_emotion_returns_zero() -> None:
    unit = _anger_brow_unit()
    assert unit.emotions.get(EmotionKind.JOY, 0.0) == 0.0


# ── NativeExpressionUnit ──────────────────────────────────────────────────────


def test_native_unit_explicit_regions() -> None:
    unit = _native_joy_unit()
    assert FacialRegion.EYE in unit.regions


# ── ExpressionHistory ─────────────────────────────────────────────────────────


def test_history_record_and_recent() -> None:
    h = ExpressionHistory(capacity=3)
    sig = ExpressionSignature(unit_ids=frozenset(["a"]), emotion=EmotionKind.JOY)
    h.record(sig)
    assert sig in h.recent()


def test_history_capacity_evicts_oldest() -> None:
    h = ExpressionHistory(capacity=2)
    s1 = ExpressionSignature(unit_ids=frozenset(["a"]), emotion=EmotionKind.JOY)
    s2 = ExpressionSignature(unit_ids=frozenset(["b"]), emotion=EmotionKind.JOY)
    s3 = ExpressionSignature(unit_ids=frozenset(["c"]), emotion=EmotionKind.JOY)
    h.record(s1)
    h.record(s2)
    h.record(s3)
    assert len(h) == 2
    assert s1 not in h.recent()
    assert s3 in h.recent()


def test_history_penalty_zero_when_empty() -> None:
    h = ExpressionHistory()
    sig = ExpressionSignature(unit_ids=frozenset(["x"]), emotion=EmotionKind.JOY)
    assert h.penalty(sig, 1.0) == 0.0


def test_history_penalty_same_combo_and_emotion() -> None:
    h = ExpressionHistory(capacity=5)
    sig = ExpressionSignature(unit_ids=frozenset(["a", "b"]), emotion=EmotionKind.JOY)
    h.record(sig)
    penalty = h.penalty(sig, 1.0)
    assert penalty > 0.5  # 相同组合应产生高惩罚


def test_history_penalty_different_emotion() -> None:
    h = ExpressionHistory(capacity=5)
    sig_joy = ExpressionSignature(unit_ids=frozenset(["a"]), emotion=EmotionKind.JOY)
    sig_anger = ExpressionSignature(unit_ids=frozenset(["a"]), emotion=EmotionKind.ANGER)
    h.record(sig_joy)
    penalty = h.penalty(sig_anger, 1.0)
    # 同 AU 但不同情绪，惩罚应低于完全相同
    assert 0.0 < penalty < 0.7


def test_history_penalty_similarity_is_exponential() -> None:
    h = ExpressionHistory(capacity=5)
    h.record(ExpressionSignature(unit_ids=frozenset(["a"]), emotion=EmotionKind.JOY))

    candidate = ExpressionSignature(unit_ids=frozenset(["a", "b"]), emotion=EmotionKind.ANGER)

    assert h.penalty(candidate, 1.0) == pytest.approx(0.325**2)


def test_history_recent_unit_ids() -> None:
    h = ExpressionHistory()
    h.record(ExpressionSignature(unit_ids=frozenset(["a", "b"]), emotion=EmotionKind.JOY))
    assert "a" in h.recent_unit_ids
    assert "b" in h.recent_unit_ids


def test_history_snapshot_restore() -> None:
    h = ExpressionHistory(capacity=5)
    sig = ExpressionSignature(unit_ids=frozenset(["a"]), emotion=EmotionKind.JOY)
    snap = h.snapshot()
    h.record(sig)
    assert len(h) == 1
    h.restore(snap)
    assert len(h) == 0


# ── ExpressionSolver ──────────────────────────────────────────────────────────


def test_solver_returns_result_for_matching_emotion() -> None:
    solver = _make_solver(_joy_unit("笑容"))
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    assert len(result.units) > 0
    assert result.emotion == EmotionKind.JOY


def test_solver_ignores_unrelated_emotion() -> None:
    solver = _make_solver(_anger_brow_unit())
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    assert len(result.units) == 0


def test_solver_semantic_targets_produced() -> None:
    solver = _make_solver(_joy_unit("笑容"))
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    assert len(result.semantic_targets) > 0
    target = result.semantic_targets[0]
    assert target.action == SemanticAction.MOUTH_SMILE
    assert 0.5 <= target.value <= 0.9


def test_solver_native_triggers_produced() -> None:
    solver = _make_solver(_native_joy_unit())
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    assert len(result.native_triggers) == 1
    assert result.native_triggers[0].native_ref == "2脸红"


def test_solver_max_units_respected() -> None:
    units = [_joy_unit(f"笑容{i}", 0.9) for i in range(10)]
    # each unit uses same action → action conflict limits to 1
    solver = _make_solver(*units)
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0, max_units=3))
    assert len(result.units) <= 3


def test_solver_mutual_exclusion_rule() -> None:
    u1 = SemanticExpressionUnit(
        id="皱眉",
        targets=[ExpressionTarget(action=SemanticAction.BROW_HEIGHT, min_value=0.0, max_value=0.2)],
        emotions={EmotionKind.ANGER: 0.9},
    )
    u2 = SemanticExpressionUnit(
        id="挑眉",
        targets=[ExpressionTarget(action=SemanticAction.BROW_HEIGHT_LEFT, min_value=0.8, max_value=1.0)],
        emotions={EmotionKind.ANGER: 0.85},
    )
    rule = MutualExclusionRule(id="眉毛互斥", unit_ids=frozenset(["皱眉", "挑眉"]))
    solver = _make_solver(u1, u2, rules=[rule])
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.ANGER, randomness=0.0))
    ids = [u.id for u in result.units]
    assert not ("皱眉" in ids and "挑眉" in ids)


def test_solver_action_conflict_implicit_mutex() -> None:
    """两个 AU 争同一个 action，只有一个应该出现"""
    u1 = SemanticExpressionUnit(
        id="大笑",
        targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.7, max_value=1.0)],
        emotions={EmotionKind.JOY: 0.95},
    )
    u2 = SemanticExpressionUnit(
        id="微笑",
        targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.4, max_value=0.6)],
        emotions={EmotionKind.JOY: 0.80},
    )
    solver = _make_solver(u1, u2)
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    smile_units = [u.id for u in result.units if u.id in ("大笑", "微笑")]
    assert len(smile_units) <= 1


def test_solver_action_overlap_implicit_mutex() -> None:
    """整体 action 与左右细分 action 互斥，避免同一部位被双重控制"""
    smile = SemanticExpressionUnit(
        id="嘴角上扬",
        targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.7, max_value=1.0)],
        emotions={EmotionKind.JOY: 0.95},
    )
    squint = SemanticExpressionUnit(
        id="眯眼",
        targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.2, max_value=0.4)],
        emotions={EmotionKind.JOY: 0.90},
    )
    wink_left = SemanticExpressionUnit(
        id="wink 左眼",
        targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN_LEFT, min_value=0.0, max_value=0.0)],
        emotions={EmotionKind.JOY: 0.88},
    )
    wink_right = SemanticExpressionUnit(
        id="wink 右眼",
        targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN_RIGHT, min_value=0.0, max_value=0.0)],
        emotions={EmotionKind.JOY: 0.87},
    )
    solver = _make_solver(smile, squint, wink_left, wink_right)

    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0, max_units=4))
    ids = {unit.id for unit in result.units}

    assert "眯眼" in ids
    assert "wink 左眼" not in ids
    assert "wink 右眼" not in ids


def test_solver_bonus_rule_score_increases() -> None:
    u1 = _joy_unit("嘴角上扬")
    u2 = SemanticExpressionUnit(
        id="眯眼",
        targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.3, max_value=0.5)],
        emotions={EmotionKind.JOY: 0.80},
    )
    rule = BonusRule(id="笑眼联动", unit_ids=frozenset(["嘴角上扬", "眯眼"]), value=0.5)
    solver_with = _make_solver(u1, u2, rules=[rule])
    solver_without = _make_solver(u1, u2)
    result_with = solver_with.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    result_without = solver_without.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    # 有 bonus 的分数应该更高（假设两者都选了这两个 AU）
    if len(result_with.units) == 2 and len(result_without.units) == 2:
        assert result_with.score >= result_without.score


def test_solver_bonus_negative_value_decreases_score() -> None:
    """Bonus 负值即旧 Penalty 语义：同框时组合得分应更低。"""
    u1 = _joy_unit("嘴角上扬")
    u2 = SemanticExpressionUnit(
        id="眯眼",
        targets=[ExpressionTarget(action=SemanticAction.EYE_OPEN, min_value=0.3, max_value=0.5)],
        emotions={EmotionKind.JOY: 0.80},
    )
    rule = BonusRule(id="矛盾联动", unit_ids=frozenset(["嘴角上扬", "眯眼"]), value=-0.5)
    solver_with = _make_solver(u1, u2, rules=[rule])
    solver_without = _make_solver(u1, u2)
    result_with = solver_with.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    result_without = solver_without.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    # 负值 bonus（=旧 Penalty）应让分数更低（假设两者都选了这两个 AU）
    if len(result_with.units) == 2 and len(result_without.units) == 2:
        assert result_with.score <= result_without.score


def test_solver_mutual_exclusion_rule_prevents_cooccurrence() -> None:
    """显式互斥：两个不共享 action 的 AU 只能靠规则禁止同现（隐式 action 冲突抓不到）。"""
    u_mouth = SemanticExpressionUnit(
        id="张嘴",
        targets=[ExpressionTarget(action=SemanticAction.MOUTH_OPEN, min_value=0.6, max_value=1.0)],
        emotions={EmotionKind.JOY: 0.90},
    )
    u_eye = SemanticExpressionUnit(
        id="瞪眼",
        targets=[ExpressionTarget(action=SemanticAction.EYE_WIDE, min_value=0.5, max_value=1.0)],
        emotions={EmotionKind.JOY: 0.85},
    )
    rule = MutualExclusionRule(id="张嘴瞪眼互斥", unit_ids=frozenset(["张嘴", "瞪眼"]))

    # 无规则：MOUTH_OPEN 与 EYE_WIDE 不重叠，隐式冲突抓不到 -> 两者可同现
    solver_without = _make_solver(u_mouth, u_eye)
    ids_without = {u.id for u in solver_without.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0)).units}
    assert {"张嘴", "瞪眼"} <= ids_without

    # 有规则：显式互斥 -> 不能同现
    solver_with = _make_solver(u_mouth, u_eye, rules=[rule])
    ids_with = {u.id for u in solver_with.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0)).units}
    assert not ({"张嘴", "瞪眼"} <= ids_with)


def test_solver_preview_does_not_update_history() -> None:
    solver = _make_solver(_joy_unit("笑容"))
    request = ExpressionRequest(emotion=EmotionKind.JOY)
    solver.preview(request)
    assert len(solver.history) == 0


def test_solver_solve_updates_history() -> None:
    solver = _make_solver(_joy_unit("笑容"))
    request = ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0)
    solver.solve(request)
    assert len(solver.history) == 1


def test_solver_units_by_region() -> None:
    solver = _make_solver(_joy_unit("笑容"))
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    if result.units:
        assert FacialRegion.MOUTH in result.units_by_region


# ── ExpressionProfileConfig ───────────────────────────────────────────────────


def test_profile_to_units_disabled_excluded() -> None:
    profile = ExpressionProfileConfig(
        semantic_units=[
            SemanticExpressionUnit(
                id="笑容",
                enabled=False,
                targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.5, max_value=0.9)],
                emotions={EmotionKind.JOY: 0.9},
            )
        ]
    )
    assert profile.to_units() == []


def test_profile_to_units_enabled_included() -> None:
    profile = ExpressionProfileConfig(
        semantic_units=[
            SemanticExpressionUnit(
                id="笑容",
                targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.5, max_value=0.9)],
                emotions={EmotionKind.JOY: 0.9},
            )
        ]
    )
    units = profile.to_units()
    assert len(units) == 1
    assert units[0].id == "笑容"


def test_profile_to_units_rejects_missing_id() -> None:
    profile = ExpressionProfileConfig(
        semantic_units=[
            SemanticExpressionUnit(
                targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.5, max_value=0.9)],
                emotions={EmotionKind.JOY: 0.9},
            )
        ]
    )
    with pytest.raises(ValueError):
        profile.to_units()


def test_profile_to_units_rejects_duplicate_id() -> None:
    unit = SemanticExpressionUnit(
        id="重复",
        targets=[ExpressionTarget(action=SemanticAction.MOUTH_SMILE, min_value=0.5, max_value=0.9)],
        emotions={EmotionKind.JOY: 0.9},
    )
    profile = ExpressionProfileConfig(semantic_units=[unit, unit])
    with pytest.raises(ValueError):
        profile.to_units()


def test_profile_to_rules() -> None:
    profile = ExpressionProfileConfig(
        rules=[
            MutualExclusionRule(id="互斥测试", unit_ids=frozenset(["a", "b"])),
            BonusRule(id="加分测试", unit_ids=frozenset(["c", "d"]), value=0.3),
            BonusRule(id="扣分测试", unit_ids=frozenset(["e"]), value=-0.2),
        ]
    )
    rules = profile.to_rules()
    assert len(rules) == 3
    assert isinstance(rules[0], MutualExclusionRule)
    assert isinstance(rules[1], BonusRule)
    assert isinstance(rules[2], BonusRule)


def test_profile_rules_discriminated_from_dict() -> None:
    """规则可凭 kind 判别从原始 dict 反序列化"""
    profile = ExpressionProfileConfig.model_validate(
        {
            "rules": [
                {"kind": "mutual_exclusion", "id": "m", "unit_ids": ["a", "b"]},
                {"kind": "bonus", "id": "b", "unit_ids": ["c"], "value": 0.3},
            ]
        }
    )
    rules = profile.to_rules()
    assert isinstance(rules[0], MutualExclusionRule)
    assert isinstance(rules[1], BonusRule)


def test_request_defaults() -> None:
    """ExpressionRequest 自带合理默认值，无需中间层填充"""
    req = ExpressionRequest(emotion=EmotionKind.JOY)
    assert req.emotion == EmotionKind.JOY
    assert req.randomness == 0.5
    assert req.max_units == 5


def test_request_overrides() -> None:
    req = ExpressionRequest(emotion=EmotionKind.ANGER, randomness=0.0, max_units=3)
    assert req.randomness == 0.0
    assert req.max_units == 3


def test_profile_native_unit_regions() -> None:
    profile = ExpressionProfileConfig(
        native_units=[
            NativeExpressionUnit(
                id="生气特效",
                platform="vtubestudio",
                native_ref="2生气",
                regions=frozenset([FacialRegion.BROW, FacialRegion.EYE]),
                emotions={EmotionKind.ANGER: 0.85},
            )
        ]
    )
    units = profile.to_units()
    assert len(units) == 1
    unit = units[0]
    assert isinstance(unit, NativeExpressionUnit)
    assert unit.id == "生气特效"
    assert FacialRegion.BROW in unit.regions
    assert FacialRegion.EYE in unit.regions


def test_profile_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        ExpressionProfileConfig.model_validate({"unknown_field": 123})


def test_unit_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        SemanticExpressionUnit.model_validate(
            {
                "targets": [{"action": "mouth.smile", "min_value": 0.5, "max_value": 0.9}],
                "bogus": 1,
            }
        )


# ── intensity（强度）插值 ───────────────────────────────────────────────────────


def _fixed_unit(uid: str, action: SemanticAction, value: float) -> SemanticExpressionUnit:
    """min==max 的固定值单元，消除随机采样以确定性验证插值"""
    return SemanticExpressionUnit(
        id=uid,
        targets=[ExpressionTarget(action=action, min_value=value, max_value=value)],
        emotions={EmotionKind.JOY: 0.95},
    )


def test_neutral_value_defaults() -> None:
    assert neutral_value(SemanticAction.EYE_OPEN) == 0.8
    assert neutral_value(SemanticAction.EYE_OPEN_LEFT) == 0.8
    assert neutral_value(SemanticAction.BROW_HEIGHT) == 0.5
    assert neutral_value(SemanticAction.MOUTH_SMILE) == 0.5
    assert neutral_value(SemanticAction.HEAD_YAW) == 0.0
    assert neutral_value(SemanticAction.MOUTH_OPEN) == 0.0
    assert neutral_value("不存在的动作") == 0.0


def test_request_intensity_default_is_one() -> None:
    assert ExpressionRequest(emotion=EmotionKind.JOY).intensity == 1.0


def test_intensity_zero_returns_neutral() -> None:
    """intensity=0：动作回归到各自静息基准，与采样值无关"""
    solver = _make_solver(_fixed_unit("大笑", SemanticAction.MOUTH_SMILE, 0.9))
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0, intensity=0.0))
    target = result.semantic_targets[0]
    assert target.value == neutral_value(SemanticAction.MOUTH_SMILE)  # 0.5


def test_intensity_half_interpolates_from_neutral() -> None:
    """intensity=0.5：value == neutral + (sampled - neutral) * 0.5"""
    solver = _make_solver(_fixed_unit("大笑", SemanticAction.MOUTH_SMILE, 0.9))
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0, intensity=0.5))
    target = result.semantic_targets[0]
    neutral = neutral_value(SemanticAction.MOUTH_SMILE)  # 0.5
    assert target.value == pytest.approx(neutral + (0.9 - neutral) * 0.5)  # 0.7


def test_intensity_one_takes_full_sample() -> None:
    """intensity=1（默认）：保留完整采样值，不受 neutral 影响"""
    solver = _make_solver(_fixed_unit("大笑", SemanticAction.MOUTH_SMILE, 0.9))
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0, intensity=1.0))
    assert result.semantic_targets[0].value == pytest.approx(0.9)


def test_intensity_zero_on_zero_neutral_action() -> None:
    """neutral=0 的动作（head.yaw），intensity=0 时回归到 0"""
    solver = _make_solver(_fixed_unit("转头", SemanticAction.HEAD_YAW, 0.7))
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0, intensity=0.0))
    assert result.semantic_targets[0].value == 0.0


# ── 典型度门控（v3）──────────────────────────────────────────────────────────


def _guest_unit(uid: str, home: EmotionKind, home_corr: float, guest: EmotionKind, guest_corr: float) -> SemanticExpressionUnit:
    """本职 home 高分、客串 guest 低分的 AU"""
    return SemanticExpressionUnit(
        id=uid,
        targets=[ExpressionTarget(action=SemanticAction.EYE_GAZE_X, min_value=-1.0, max_value=1.0)],
        emotions={home: home_corr, guest: guest_corr},
    )


def test_typicality_hard_gate_blocks_guest_au() -> None:
    """悲伤专业户（sad .72）客串 joy（.12）：典型度 0.17 < 0.30，任何随机度下都不入选"""
    muyi = _guest_unit("目移", EmotionKind.SADNESS, 0.72, EmotionKind.JOY, 0.12)
    smile = _joy_unit("嘴角上扬", 0.82)
    for seed in range(30):
        solver = ExpressionSolver(
            units=[smile, muyi],
            rules=[],
            history=ExpressionHistory(capacity=10),
            rng=random.Random(seed),
        )
        result = solver.preview(ExpressionRequest(emotion=EmotionKind.JOY))
        assert "目移" not in {u.id for u in result.units}


def test_typicality_gate_disabled_restores_reachability() -> None:
    """τ=0 且 α=0 时完全退化：客串 AU 重新可达（回归旧行为的逃生门）"""
    muyi = _guest_unit("目移", EmotionKind.SADNESS, 0.72, EmotionKind.JOY, 0.12)
    solver = ExpressionSolver(
        units=[muyi],
        rules=[],
        history=ExpressionHistory(capacity=10),
        typicality_floor=0.0,
        typicality_power=0.0,
    )
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    assert "目移" in {u.id for u in result.units}


def test_baseline_unit_cannot_anchor() -> None:
    """只有百搭候选时无锚可立，返回空表情"""
    tilt = SemanticExpressionUnit(
        id="歪头",
        targets=[ExpressionTarget(action=SemanticAction.HEAD_ROLL, min_value=-0.5, max_value=0.5)],
        emotions={},
        baseline=0.9,
    )
    solver = _make_solver(tilt)
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    assert result.units == []


def test_baseline_unit_rides_along_behind_anchor() -> None:
    """有正主坐锚后，百搭候选正常搭车"""
    tilt = SemanticExpressionUnit(
        id="歪头",
        targets=[ExpressionTarget(action=SemanticAction.HEAD_ROLL, min_value=-0.5, max_value=0.5)],
        emotions={},
        baseline=0.6,
    )
    solver = _make_solver(_joy_unit("嘴角上扬", 0.9), tilt)
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    ids = {u.id for u in result.units}
    assert {"嘴角上扬", "歪头"} <= ids


def test_explicit_zero_disables_baseline() -> None:
    """显式打 0 优先于百搭分：该情绪彻底禁用"""
    tilt = SemanticExpressionUnit(
        id="歪头",
        targets=[ExpressionTarget(action=SemanticAction.HEAD_ROLL, min_value=-0.5, max_value=0.5)],
        emotions={EmotionKind.JOY: 0.0},
        baseline=0.6,
    )
    solver = _make_solver(_joy_unit("嘴角上扬", 0.9), tilt)
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.JOY, randomness=0.0))
    assert "歪头" not in {u.id for u in result.units}


def test_typical_home_emotion_passes_gate() -> None:
    """本职情绪（典型度 1.0）不受门控影响"""
    muyi = _guest_unit("目移", EmotionKind.SADNESS, 0.72, EmotionKind.JOY, 0.12)
    solver = _make_solver(muyi)
    result = solver.solve(ExpressionRequest(emotion=EmotionKind.SADNESS, randomness=0.0))
    assert "目移" in {u.id for u in result.units}

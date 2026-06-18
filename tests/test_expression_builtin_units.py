"""验证模型配置文件中内置 AU 可加载并解算出合理表情"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from livestudio.services.expression import (
    EmotionKind,
    ExpressionHistory,
    ExpressionProfileConfig,
    ExpressionSolver,
)
from livestudio.services.platforms.vtubestudio import VTubeStudioModelConfig

_MODEL_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "models"
    / "vtubestudio"
    / "Pink_devil_2be06.yaml"
)


def _load_profile() -> ExpressionProfileConfig:
    raw = yaml.safe_load(_MODEL_CONFIG.read_text(encoding="utf-8"))
    config = VTubeStudioModelConfig.model_validate(raw)
    return config.expression_profile


def _solver(profile: ExpressionProfileConfig) -> ExpressionSolver:
    return ExpressionSolver(
        units=profile.to_units(),
        rules=profile.to_rules(),
        history=ExpressionHistory(capacity=profile.runtime.history_capacity),
        top_candidates=profile.runtime.top_candidates,
    )


def test_model_config_full_deserialization() -> None:
    """整份模型 YAML（含 expression_profile）能被严格校验"""
    raw = yaml.safe_load(_MODEL_CONFIG.read_text(encoding="utf-8"))
    config = VTubeStudioModelConfig.model_validate(raw)
    assert config.expression_profile.semantic_units
    assert config.expression_profile.native_units
    assert config.expression_profile.rules


def test_builtin_units_present() -> None:
    profile = _load_profile()
    units = profile.to_units()
    assert len(units) >= 10
    ids = {u.id for u in units}
    assert "嘴角上扬" in ids
    assert "皱眉" in ids


@pytest.mark.parametrize(
    "emotion",
    [
        EmotionKind.JOY,
        EmotionKind.SADNESS,
        EmotionKind.ANGER,
        EmotionKind.SURPRISE,
        EmotionKind.FEAR,
        EmotionKind.NEUTRAL,
    ],
)
def test_each_emotion_produces_expression(emotion: EmotionKind) -> None:
    """每个情绪都应解算出至少一个 AU"""
    profile = _load_profile()
    solver = _solver(profile)
    request = profile.build_request(emotion, randomness=0.0)
    result = solver.solve(request)
    assert len(result.units) > 0, f"情绪 {emotion} 未解算出任何 AU"
    assert result.emotion == emotion


def test_joy_drives_smile() -> None:
    """喜悦应当驱动嘴角上扬语义动作"""
    profile = _load_profile()
    solver = _solver(profile)
    result = solver.solve(profile.build_request(EmotionKind.JOY, randomness=0.0))
    actions = {t.action for t in result.semantic_targets}
    assert "mouth.smile" in actions


def test_anger_triggers_native_when_strong() -> None:
    """愤怒相关性高，应触发生气原生特效"""
    profile = _load_profile()
    solver = _solver(profile)
    result = solver.solve(profile.build_request(EmotionKind.ANGER, randomness=0.0))
    refs = {t.native_ref for t in result.native_triggers}
    assert "2生气" in refs


def test_brow_mutual_exclusion_holds() -> None:
    """眉毛互斥规则：解算结果不应同时含多个眉毛 AU"""
    profile = _load_profile()
    solver = _solver(profile)
    brow_units = {"挑眉", "皱眉", "垂眉", "自然眉"}
    for emotion in EmotionKind:
        result = solver.solve(profile.build_request(emotion, randomness=0.0))
        selected_brows = brow_units & {u.id for u in result.units}
        assert len(selected_brows) <= 1, f"{emotion} 选中多个眉毛 AU: {selected_brows}"


def test_no_action_conflict_in_result() -> None:
    """同一语义动作不应被多个 AU 同时写入"""
    profile = _load_profile()
    solver = _solver(profile)
    for emotion in EmotionKind:
        result = solver.solve(profile.build_request(emotion, randomness=0.0))
        seen: set[str] = set()
        for target in result.semantic_targets:
            assert target.action not in seen, f"{emotion} 动作冲突: {target.action}"
            seen.add(target.action)


def test_diversity_across_repeated_solves() -> None:
    """连续多次解算同一情绪，应产生多于一种组合（多样性）"""
    profile = _load_profile()
    solver = _solver(profile)
    combos = set()
    for _ in range(20):
        result = solver.solve(profile.build_request(EmotionKind.JOY))
        combos.add(frozenset(u.id for u in result.units))
    assert len(combos) > 1

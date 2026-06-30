"""验证内置默认 AU 仅在首次初始化时种入配置文件"""

from __future__ import annotations

from pathlib import Path

import yaml

from livestudio.config import ConfigManager
from livestudio.services.expression import (
    EmotionKind,
    ExpressionHistory,
    ExpressionProfileConfig,
    ExpressionRequest,
    ExpressionSolver,
    default_rules,
    default_semantic_units,
)
from livestudio.services.platforms.model import PlatformModelIdentity
from livestudio.services.platforms.vtubestudio import VTubeStudioModelConfig


def _solver(profile: ExpressionProfileConfig) -> ExpressionSolver:
    return ExpressionSolver(
        units=profile.to_units(),
        rules=profile.to_rules(),
        history=ExpressionHistory(),
    )


# ── 默认目录内容 ──────────────────────────────────────────────────────────────


def test_default_semantic_units_are_pure_semantic() -> None:
    """默认 AU 必须全是语义 AU，不含平台特定原生表情"""
    units = default_semantic_units()
    assert len(units) >= 10
    for unit in units:
        assert unit.id  # 默认 AU 必须自带 id
        assert unit.targets  # 语义 AU 一定有 targets


def test_default_units_fresh_instances() -> None:
    """每次调用返回新实例，避免共享可变状态"""
    a = default_semantic_units()
    b = default_semantic_units()
    assert a is not b
    assert a[0] is not b[0]


def test_create_default_builds_solvable_profile() -> None:
    profile = ExpressionProfileConfig.create_default()
    assert profile.semantic_units
    assert profile.rules
    solver = _solver(profile)
    for emotion in EmotionKind:
        result = solver.solve(ExpressionRequest(emotion=emotion, randomness=0.0))
        assert len(result.units) > 0, f"{emotion} 未解算出 AU"


def test_default_anger_emphasizes_brow_and_eye() -> None:
    profile = ExpressionProfileConfig.create_default()
    solver = _solver(profile)

    result = solver.solve(ExpressionRequest(emotion=EmotionKind.ANGER, randomness=0.0))
    ids = {unit.id for unit in result.units}

    assert {"皱眉", "眯眼", "抿嘴"} <= ids


def test_default_sadness_emphasizes_downcast_face() -> None:
    profile = ExpressionProfileConfig.create_default()
    solver = _solver(profile)

    result = solver.solve(ExpressionRequest(emotion=EmotionKind.SADNESS, randomness=0.0))
    ids = {unit.id for unit in result.units}

    assert "嘴角下撇" in ids
    assert "眼睛下看" in ids or "低头" in ids


def test_default_rules_reference_existing_units() -> None:
    """默认规则引用的 unit_id 必须都在默认 AU 中存在"""
    unit_ids = {unit.id for unit in default_semantic_units()}
    for rule in default_rules():
        for uid in rule.unit_ids:
            assert uid in unit_ids, f"规则 {rule.id} 引用了不存在的 AU: {uid}"


def test_default_rules_make_left_and_right_wink_mutex() -> None:
    rule = next(rule for rule in default_rules() if rule.id == "wink 左右互斥")
    assert rule.unit_ids == frozenset({"wink 左眼", "wink 右眼"})


# ── create_default 种子机制 ────────────────────────────────────────────────────


def test_create_default_seeds_expression_profile() -> None:
    identity = PlatformModelIdentity(
        platform_name="vtubestudio",
        model_id="m1",
        model_name="测试模型",
    )
    config = VTubeStudioModelConfig.create_default(identity)
    assert config.expression_profile.semantic_units
    assert config.expression_profile.rules
    # VTS 子类的语义 profile / 参数也应保留
    assert config.semantic_profile.bindings
    assert config.parameter_specs
    # 空构造仍是空的（seed-once 内容只经 create_default 注入）
    assert VTubeStudioModelConfig().expression_profile.semantic_units == []


async def test_first_load_writes_defaults(tmp_path: Path) -> None:
    """配置文件不存在时，首次加载写入默认 AU"""
    config_path = tmp_path / "new_model.yaml"
    default_config = VTubeStudioModelConfig.create_default(
        PlatformModelIdentity(
            platform_name="vtubestudio",
            model_id="m1",
            model_name="测试模型",
        )
    )
    manager = ConfigManager(
        VTubeStudioModelConfig,
        config_path,
        default_config=default_config,
    )
    config = await manager.reload()
    assert config.expression_profile.semantic_units
    # 文件已落盘且含默认 AU
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    ids = {u["id"] for u in raw["expression_profile"]["semantic_units"]}
    assert "嘴角上扬" in ids


async def test_existing_file_not_overwritten_by_defaults(tmp_path: Path) -> None:
    """文件已存在时，加载以文件为准，不被默认值覆盖"""
    config_path = tmp_path / "existing.yaml"
    # 预置一份只有一个自定义 AU 的配置
    config_path.write_text(
        yaml.safe_dump(
            {
                "expression_profile": {
                    "semantic_units": [
                        {
                            "id": "我的专属笑",
                            "targets": [
                                {
                                    "action": "mouth.smile",
                                    "min_value": 0.5,
                                    "max_value": 0.7,
                                }
                            ],
                            "emotions": {"joy": 0.9},
                        }
                    ]
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    default_config = VTubeStudioModelConfig.create_default(
        PlatformModelIdentity(
            platform_name="vtubestudio",
            model_id="m1",
            model_name="测试模型",
        )
    )
    manager = ConfigManager(
        VTubeStudioModelConfig,
        config_path,
        default_config=default_config,
    )
    config = await manager.reload()

    # 以文件为准：只有自定义 AU，没有默认 AU 混入
    ids = {u.id for u in config.expression_profile.semantic_units}
    assert "我的专属笑" in ids
    assert "嘴角上扬" not in ids

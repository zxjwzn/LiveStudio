"""表情解算层接入运行时的集成测试"""

from __future__ import annotations

from collections.abc import Iterable

from livestudio.clients.vtube_studio.models import ExpressionActivationRequest
from livestudio.services.animations.controllers import (
    ExpressionController,
    ExpressionControllerSettings,
)
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.expression import (
    EmotionKind,
    ExpressionProfileConfig,
    NativeExpressionTrigger,
)
from livestudio.services.platforms.vtubestudio.expression_adapter import (
    VTSExpressionAdapter,
)
from livestudio.services.semantic_actions import SemanticAction
from tests.conftest import _SemanticPlatform, _TemplatePlayer


class _ExpressionPlatform(_SemanticPlatform):
    """在语义平台基础上记录原生表情触发"""

    def __init__(self, name: str = "expression-test") -> None:
        super().__init__(name)
        self.native_calls: list[list[NativeExpressionTrigger]] = []

    async def apply_native_expressions(self, triggers: Iterable[NativeExpressionTrigger]) -> None:
        self.native_calls.append(list(triggers))


class _FakeExpressionClient:
    """记录 set_expression_active 调用的假客户端"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    async def set_expression_active(self, request: ExpressionActivationRequest) -> object:
        self.calls.append((request.data.expression_file, request.data.active))
        return object()


def _runtime(platform: _SemanticPlatform) -> PlatformAnimationRuntime:
    return PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )


def _joy_profile() -> ExpressionProfileConfig:
    return ExpressionProfileConfig.model_validate(
        {
            "runtime": {"randomness": 0.0},
            "semantic_units": [
                {
                    "id": "嘴角上扬",
                    "targets": [
                        {
                            "action": "mouth.smile",
                            "min_value": 0.6,
                            "max_value": 0.6,
                        }
                    ],
                    "emotions": {"joy": 0.95},
                }
            ],
            "native_units": [
                {
                    "id": "脸红",
                    "platform": "vtubestudio",
                    "native_ref": "2脸红",
                    "regions": ["eye"],
                    "emotions": {"joy": 0.9},
                }
            ],
        }
    )


# ── VTSExpressionAdapter ──────────────────────────────────────────────────────


async def test_adapter_activates_mapped_expression() -> None:
    client = _FakeExpressionClient()
    adapter = VTSExpressionAdapter(name_to_file={"2脸红": "2脸红.exp3.json"})
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="2脸红")],
        client,
    )
    assert client.calls == [("2脸红.exp3.json", True)]
    assert adapter.active_files == frozenset({"2脸红.exp3.json"})


async def test_adapter_diff_only_changes() -> None:
    client = _FakeExpressionClient()
    adapter = VTSExpressionAdapter(name_to_file={"A": "A.exp3.json", "B": "B.exp3.json"})
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="A")],
        client,
    )
    # 第二次切换到 B：A 关闭，B 激活
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="B")],
        client,
    )
    assert client.calls == [
        ("A.exp3.json", True),
        ("A.exp3.json", False),
        ("B.exp3.json", True),
    ]


async def test_adapter_no_redundant_calls_when_unchanged() -> None:
    client = _FakeExpressionClient()
    adapter = VTSExpressionAdapter(name_to_file={"A": "A.exp3.json"})
    trigger = [NativeExpressionTrigger(platform="vtubestudio", native_ref="A")]
    await adapter.apply(trigger, client)
    await adapter.apply(trigger, client)
    # 第二次相同，不应再次调用
    assert client.calls == [("A.exp3.json", True)]


async def test_adapter_accepts_direct_file_ref() -> None:
    client = _FakeExpressionClient()
    adapter = VTSExpressionAdapter()
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="X.exp3.json")],
        client,
    )
    assert client.calls == [("X.exp3.json", True)]


async def test_adapter_skips_unresolvable_and_foreign_platform() -> None:
    client = _FakeExpressionClient()
    adapter = VTSExpressionAdapter()
    await adapter.apply(
        [
            NativeExpressionTrigger(platform="vtubestudio", native_ref="未知表情"),
            NativeExpressionTrigger(platform="warudo", native_ref="X.exp3.json"),
        ],
        client,
    )
    assert client.calls == []


async def test_adapter_clears_when_empty() -> None:
    client = _FakeExpressionClient()
    adapter = VTSExpressionAdapter(name_to_file={"A": "A.exp3.json"})
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="A")],
        client,
    )
    await adapter.apply([], client)
    assert client.calls == [("A.exp3.json", True), ("A.exp3.json", False)]
    assert adapter.active_files == frozenset()


# ── ExpressionController ──────────────────────────────────────────────────────


async def test_controller_is_oneshot() -> None:
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),
        ExpressionProfileConfig(),
    )
    assert controller.animation_type.value == "oneshot"


async def test_controller_emits_semantic_and_native() -> None:
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),
        _joy_profile(),
    )

    await controller.execute(emotion=EmotionKind.JOY)

    actions = {req.action_parameter_name for req in platform.requests}
    assert SemanticAction.MOUTH_SMILE.value in actions
    assert all(req.start_value is None for req in platform.requests)
    # 原生触发被传给平台
    assert platform.native_calls
    refs = {t.native_ref for call in platform.native_calls for t in call}
    assert "2脸红" in refs


async def test_controller_emits_transition_then_hold() -> None:
    """每个语义动作应有两段：过渡(transition_duration) + 保持(hold_duration)"""
    platform = _ExpressionPlatform()
    profile = ExpressionProfileConfig.model_validate(
        {
            "runtime": {"randomness": 0.0, "transition_duration": 0.5, "hold_duration": 1.5},
            "semantic_units": [
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.6, "max_value": 0.6}],
                    "emotions": {"joy": 0.95},
                }
            ],
        }
    )
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(au_priority=99),
        profile,
    )
    await controller.execute(emotion=EmotionKind.JOY)

    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert len(smile) == 2
    transition, hold = smile
    assert transition.duration == 0.5
    assert hold.duration == 1.5
    # 两段同一目标值，且都用配置的高优先级锁定
    assert transition.end_value == hold.end_value
    assert transition.priority == 99
    assert hold.priority == 99


async def test_controller_skips_hold_when_zero() -> None:
    platform = _ExpressionPlatform()
    profile = ExpressionProfileConfig.model_validate(
        {
            "runtime": {"randomness": 0.0, "hold_duration": 0.0},
            "semantic_units": [
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.6, "max_value": 0.6}],
                    "emotions": {"joy": 0.95},
                }
            ],
        }
    )
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),
        profile,
    )
    await controller.execute(emotion=EmotionKind.JOY)
    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert len(smile) == 1  # 只有过渡段


async def test_controller_accepts_string_emotion() -> None:
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),
        _joy_profile(),
    )
    await controller.execute(emotion="joy")
    assert platform.requests


async def test_controller_ignores_invalid_emotion() -> None:
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),
        _joy_profile(),
    )
    await controller.execute(emotion="not_an_emotion")
    assert platform.requests == []
    assert platform.native_calls == []


async def test_controller_uses_unit_easing() -> None:
    platform = _ExpressionPlatform()
    profile = ExpressionProfileConfig.model_validate(
        {
            "runtime": {"randomness": 0.0, "hold_duration": 0.0},
            "semantic_units": [
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.6, "max_value": 0.6}],
                    "emotions": {"joy": 0.95},
                    "easing": "in_out_sine",
                }
            ],
        }
    )
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),
        profile,
    )
    await controller.execute(emotion=EmotionKind.JOY)
    assert platform.requests
    assert all(req.easing == "in_out_sine" for req in platform.requests)


# ── PlatformService 默认实现 ──────────────────────────────────────────────────


async def test_base_apply_native_expressions_is_noop() -> None:
    platform = _SemanticPlatform()
    # 基类默认无操作，不应抛异常
    await platform.apply_native_expressions([NativeExpressionTrigger(platform="vtubestudio", native_ref="X")])

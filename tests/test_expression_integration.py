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
        self.native_fade_times: list[float | None] = []

    async def apply_native_expressions(
        self,
        triggers: Iterable[NativeExpressionTrigger],
        *,
        fade_time: float | None = None,
    ) -> None:
        self.native_calls.append(list(triggers))
        self.native_fade_times.append(fade_time)


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


async def _drain(controller: ExpressionController) -> None:
    """等待 execute 丢到后台的收尾任务跑完（过渡+保持+停用）

    测试里的 tween_semantic 是即时 stub，后台任务会立刻推进完毕。
    """

    task = controller.finishing_task
    if task is not None:
        await task


def _joy_profile() -> ExpressionProfileConfig:
    return ExpressionProfileConfig.model_validate(
        {
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
    await _drain(controller)

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
        ExpressionControllerSettings(au_priority=99, transition_duration=0.5, hold_duration=1.5),
        profile,
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)

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
        ExpressionControllerSettings(hold_duration=0.0),
        profile,
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)
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
    await _drain(controller)
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
        ExpressionControllerSettings(hold_duration=0.0),
        profile,
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)
    assert platform.requests
    assert all(req.easing == "in_out_sine" for req in platform.requests)


# ── PlatformService 默认实现 ──────────────────────────────────────────────────


async def test_base_apply_native_expressions_is_noop() -> None:
    platform = _SemanticPlatform()
    # 基类默认无操作，不应抛异常
    await platform.apply_native_expressions([NativeExpressionTrigger(platform="vtubestudio", native_ref="X")])


# ── 原生表情 fade / 收尾停用 / 后台任务取消 ─────────────────────────────────────


async def test_native_activation_fade_matches_transition() -> None:
    """激活原生表情时，fade_time 应与 transition_duration 一致"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(transition_duration=0.7, hold_duration=0.0),
        _joy_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY)
    # 第一次 apply 是激活，fade 应为 transition_duration
    assert platform.native_fade_times[0] == 0.7
    await _drain(controller)


async def test_native_deactivated_after_hold() -> None:
    """保持结束后，收尾应再 apply（空列表）停用本次激活的原生表情"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(transition_duration=0.0, hold_duration=0.0),
        _joy_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)
    # 至少两次 apply：激活 + 收尾停用（空）
    assert len(platform.native_calls) >= 2
    assert platform.native_calls[0]  # 激活非空
    assert platform.native_calls[-1] == []  # 收尾停用为空列表


async def test_new_execute_cancels_previous_finishing() -> None:
    """新 execute 进来时应取消上一个未结束的后台收尾任务"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        # 长保持，确保第一次的后台任务还在进行中
        ExpressionControllerSettings(transition_duration=0.0, hold_duration=10.0),
        _joy_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY)
    first_task = controller.finishing_task
    assert first_task is not None
    assert not first_task.done()

    # 第二次 execute 应取消第一个后台任务
    await controller.execute(emotion=EmotionKind.JOY)
    assert first_task.cancelled() or first_task.done()
    # 取消后不应执行收尾停用（避免误停本次激活的表情）
    # 第一个任务被取消，native_calls 里不应出现因它而来的空列表停用
    second_task = controller.finishing_task
    assert second_task is not first_task

    await controller.cancel()


async def test_pure_native_deactivated_via_sleep() -> None:
    """纯原生表情（无语义目标）也应在窗口结束后停用"""
    platform = _ExpressionPlatform()
    profile = ExpressionProfileConfig.model_validate(
        {
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
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(transition_duration=0.0, hold_duration=0.0),
        profile,
    )
    await controller.execute(emotion=EmotionKind.JOY)
    assert not platform.requests  # 无语义缓动
    await _drain(controller)
    assert platform.native_calls[-1] == []  # 收尾停用


# ── 回归自然表情 ───────────────────────────────────────────────────────────────


def _joy_and_neutral_profile() -> ExpressionProfileConfig:
    """同时含 JOY 与 NEUTRAL 语义 AU，且驱动不同 action 便于区分"""
    return ExpressionProfileConfig.model_validate(
        {
            "semantic_units": [
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.6, "max_value": 0.6}],
                    "emotions": {"joy": 0.95},
                },
                {
                    "id": "自然眉",
                    "targets": [{"action": "brow.height", "min_value": 0.5, "max_value": 0.5}],
                    "emotions": {"neutral": 0.9},
                },
            ],
        }
    )


async def test_returns_to_neutral_after_hold() -> None:
    """非中性情绪保持结束后，应解算 NEUTRAL 并缓动回自然表情"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(transition_duration=0.0, hold_duration=0.0),
        _joy_and_neutral_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)

    actions = [req.action_parameter_name for req in platform.requests]
    # 先有 JOY 的 mouth.smile，最后回归 NEUTRAL 的 brow.height
    assert SemanticAction.MOUTH_SMILE.value in actions
    assert SemanticAction.BROW_HEIGHT.value in actions
    assert actions[-1] == SemanticAction.BROW_HEIGHT.value


async def test_neutral_emotion_does_not_loop_return() -> None:
    """本次就是 NEUTRAL 时不应再触发一次回归"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(transition_duration=0.0, hold_duration=0.0),
        _joy_and_neutral_profile(),
    )
    await controller.execute(emotion=EmotionKind.NEUTRAL)
    await _drain(controller)

    actions = [req.action_parameter_name for req in platform.requests]
    # 只解算了一次 NEUTRAL（brow.height），不应出现重复的回归段
    assert actions == [SemanticAction.BROW_HEIGHT.value]


async def test_return_to_neutral_disabled() -> None:
    """return_to_neutral=False 时保持结束后不回归"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(
            transition_duration=0.0, hold_duration=0.0, return_to_neutral=False
        ),
        _joy_and_neutral_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)

    actions = [req.action_parameter_name for req in platform.requests]
    # 只有 JOY，不应出现 NEUTRAL 的 brow.height
    assert SemanticAction.BROW_HEIGHT.value not in actions


async def test_return_to_neutral_not_held() -> None:
    """回归段只过渡、不保持：NEUTRAL 的 action 只下发一段"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(transition_duration=0.0, hold_duration=1.5),
        _joy_and_neutral_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)

    brow = [r for r in platform.requests if r.action_parameter_name == SemanticAction.BROW_HEIGHT.value]
    assert len(brow) == 1  # 回归只过渡一段，无保持段

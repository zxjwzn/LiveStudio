"""表情解算层接入运行时的集成测试"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from livestudio.clients.vtube_studio.models import ExpressionActivationRequest
from livestudio.services.animations.controllers import (
    ExpressionController,
    ExpressionControllerSettings,
)
from livestudio.services.animations.controllers.constants import (
    EXPRESSION_AU_PRIORITY,
    EXPRESSION_NEUTRAL_PRIORITY,
)
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.expression import (
    EmotionKind,
    ExpressionProfileConfig,
    ExpressionRequest,
    NativeExpressionTrigger,
)
from livestudio.services.platforms.vtubestudio.expression_adapter import (
    VTSExpressionAdapter,
)
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticAction,
    SemanticActionAdapter,
    SemanticActionBinding,
    SemanticActionProfile,
)
from tests.conftest import _SemanticPlatform, _TemplatePlayer


class _ExpressionPlatform(_SemanticPlatform):
    """在语义平台基础上记录原生表情触发"""

    def __init__(self, name: str = "expression-test") -> None:
        super().__init__(name)
        self.native_calls: list[list[NativeExpressionTrigger]] = []
        self.native_fade_times: list[float | None] = []
        self._semantic_adapter: SemanticActionAdapter | None = None

    @property
    def semantic_adapter(self) -> SemanticActionAdapter | None:
        return self._semantic_adapter

    def bind_semantic_actions(self, actions: Iterable[SemanticAction]) -> None:
        specs: list[PlatformParameterSpec] = []
        bindings: list[SemanticActionBinding] = []
        for action in actions:
            param_name = f"Param{len(specs)}"
            specs.append(PlatformParameterSpec(name=param_name, minimum=0.0, maximum=1.0))
            bindings.append(SemanticActionBinding(action=action, platform_params=[param_name]))
        self._semantic_adapter = SemanticActionAdapter(
            SemanticActionProfile(bindings=bindings),
            parameter_specs=specs,
            engine=self.tween,
        )

    async def apply_native_expressions(
        self,
        triggers: Iterable[NativeExpressionTrigger],
        *,
        fade_time: float | None = None,
        scope: str = "default",  # noqa: ARG002
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
    """等待 hold + restore 后台任务跑完。"""

    for attr in ("finishing_task", "_hold_task", "_restore_task"):
        task = getattr(controller, attr, None)
        if task is not None and not task.done():
            await task
    # fire-and-forget 可能刚 spawn
    for _ in range(5):
        task = getattr(controller, "_restore_task", None)
        if task is not None and not task.done():
            await task
        else:
            break
        await asyncio.sleep(0)


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
                    # 0.85：仍 ≥0.80 故必被选中，但单单元情绪满足度 < 0.90，
                    # 不会触发 solver 的「饱和提前收手」，保证两个单元都进组合（测试需要两者）。
                    "emotions": {"joy": 0.85},
                }
            ],
            "native_units": [
                {
                    "id": "脸红",
                    "platform": "vtubestudio",
                    "native_ref": "2脸红",
                    "regions": ["eye"],
                    "emotions": {"joy": 0.85},
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


async def test_adapter_scopes_do_not_interfere() -> None:
    """不同作用域各管各的：情绪解算清空自己那组时不应关掉手动点亮的表情"""
    client = _FakeExpressionClient()
    adapter = VTSExpressionAdapter(name_to_file={"A": "A.exp3.json", "B": "B.exp3.json"})
    # 手动点亮 A（manual 作用域）
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="A")],
        client,
        scope="manual",
    )
    # 情绪解算激活 B（emotion 作用域）
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="B")],
        client,
        scope="emotion",
    )
    # 情绪解算收尾清空自己那组（空列表）
    await adapter.apply([], client, scope="emotion")
    # A 始终保持激活，只有 B 经历了激活→停用
    assert client.calls == [
        ("A.exp3.json", True),
        ("B.exp3.json", True),
        ("B.exp3.json", False),
    ]
    assert adapter.active_files == frozenset({"A.exp3.json"})


async def test_adapter_union_no_redundant_deactivate_across_scopes() -> None:
    """两个作用域想要同一文件时，单个作用域清空不应停用仍被另一作用域需要的文件"""
    client = _FakeExpressionClient()
    adapter = VTSExpressionAdapter(name_to_file={"A": "A.exp3.json"})
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="A")],
        client,
        scope="manual",
    )
    await adapter.apply(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="A")],
        client,
        scope="emotion",
    )
    # emotion 清空，但 manual 仍要 A，故不应有停用调用
    await adapter.apply([], client, scope="emotion")
    assert client.calls == [("A.exp3.json", True)]
    assert adapter.active_files == frozenset({"A.exp3.json"})


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


async def test_controller_execute_uses_per_call_durations() -> None:
    """execute 的 transition_duration/hold_duration 覆盖配置缺省;原生 fade_time 跟随过渡时长。"""

    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),  # transition=0.5, hold=1.0, neutral=0.5
        _joy_profile(),
    )

    await controller.execute(emotion=EmotionKind.JOY, transition_duration=0.3, hold_duration=2.0)
    await _drain(controller)

    # 过渡段(0.3) + 保持段(2.0) + 回归段(配置 0.5)三段缓动的 duration
    assert [req.duration for req in platform.requests] == [0.3, 2.0, 0.5]
    # 原生表情激活/停用的 fade_time 跟随本次过渡时长(0.3)
    assert platform.native_fade_times == [0.3, 0.3]


async def test_controller_filters_unbound_semantic_units_before_solving() -> None:
    platform = _ExpressionPlatform()
    platform.bind_semantic_actions([SemanticAction.MOUTH_SMILE])
    profile = ExpressionProfileConfig.model_validate(
        {
            "semantic_units": [
                {
                    "id": "瞪眼",
                    "targets": [{"action": "eye.wide", "min_value": 1.0, "max_value": 1.0}],
                    "emotions": {"surprise": 0.99},
                },
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.8, "max_value": 0.8}],
                    "emotions": {"surprise": 0.8},
                },
            ]
        }
    )
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),
        profile,
    )

    selected = controller.solver.preview(ExpressionRequest(emotion=EmotionKind.SURPRISE, randomness=0.0, max_units=5))

    assert [unit.id for unit in selected.units] == ["嘴角上扬"]
    assert [target.action for target in selected.semantic_targets] == [SemanticAction.MOUTH_SMILE]


async def test_controller_filters_unit_when_any_semantic_target_is_unbound() -> None:
    platform = _ExpressionPlatform()
    platform.bind_semantic_actions([SemanticAction.MOUTH_SMILE])
    profile = ExpressionProfileConfig.model_validate(
        {
            "semantic_units": [
                {
                    "id": "复合表情",
                    "targets": [
                        {"action": "mouth.smile", "min_value": 0.8, "max_value": 0.8},
                        {"action": "eye.wide", "min_value": 1.0, "max_value": 1.0},
                    ],
                    "emotions": {"surprise": 0.99},
                },
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.7, "max_value": 0.7}],
                    "emotions": {"surprise": 0.8},
                },
            ]
        }
    )
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(),
        profile,
    )

    selected = controller.solver.preview(ExpressionRequest(emotion=EmotionKind.SURPRISE, randomness=0.0, max_units=5))

    assert [unit.id for unit in selected.units] == ["嘴角上扬"]
    assert [target.action for target in selected.semantic_targets] == [SemanticAction.MOUTH_SMILE]


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
        ExpressionControllerSettings(
            transition_duration=0.5,
            hold_duration=1.5,
        ),
        profile,
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)

    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert len(smile) == 3
    transition, hold, neutral = smile
    assert transition.duration == 0.5
    assert hold.duration == 1.5
    assert neutral.duration == 0.5
    assert transition.end_value == hold.end_value
    assert neutral.end_value == 0.5
    # 过渡/保持段受 EXPRESSION_AU_PRIORITY 保护，表情展示期不被待机控制器打断；
    # 回归段降到 EXPRESSION_NEUTRAL_PRIORITY，低于各待机控制器（默认 10），使其在
    # AU 解算收尾时即时按参数接管，无人接管的参数照常回静息。
    assert transition.priority == EXPRESSION_AU_PRIORITY
    assert hold.priority == EXPRESSION_AU_PRIORITY
    assert neutral.priority == EXPRESSION_NEUTRAL_PRIORITY


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
    assert len(smile) == 2  # 过渡段 + 回归段
    assert smile[-1].end_value == 0.5


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
    # 字符串情绪被正确解析并产出了一套表情。解算可能只挑中单个「完整」单元，
    # 它既可能是语义 AU（→ requests），也可能是原生表情（→ native triggers），
    # 故两者任一非空即算通过，避免对单元类型做过强假设。
    produced_semantic = bool(platform.requests)
    produced_native = any(call for call in platform.native_calls)
    assert produced_semantic or produced_native


async def test_controller_intensity_zero_drives_neutral() -> None:
    """execute 透传 intensity=0：本次驱动的 mouth.smile 直接落到静息基准 0.5"""
    platform = _ExpressionPlatform()
    profile = ExpressionProfileConfig.model_validate(
        {
            "semantic_units": [
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.9, "max_value": 0.9}],
                    "emotions": {"joy": 0.95},
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
    await controller.execute(emotion=EmotionKind.JOY, intensity=0.0)
    await _drain(controller)
    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert smile
    assert all(r.end_value == 0.5 for r in smile)


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


# ── 回归静息 ───────────────────────────────────────────────────────────────────


def _joy_return_profile() -> ExpressionProfileConfig:
    """单个 JOY 语义 AU，驱动 mouth.smile，便于验证回归静息"""
    return ExpressionProfileConfig.model_validate(
        {
            "semantic_units": [
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.6, "max_value": 0.6}],
                    "emotions": {"joy": 0.95},
                },
            ],
        }
    )


async def test_returns_to_neutral_after_hold() -> None:
    """非中性情绪保持结束后，应把本次驱动过的参数缓动回各自静息基准"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(transition_duration=0.0, hold_duration=0.0),
        _joy_return_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)

    # JOY 驱动 mouth.smile=0.6；回归段把它拉回静息基准 0.5
    smile_reqs = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert smile_reqs
    assert smile_reqs[-1].end_value == 0.5


async def test_neutral_return_not_held() -> None:
    """回归段只过渡、不保持：driven 动作在过渡+保持两段后，回归段只再下发一段到静息"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(transition_duration=0.0, hold_duration=1.5),
        _joy_return_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY)
    await _drain(controller)

    # mouth.smile：过渡段 + 保持段 + 回归段 = 3 段；末段为回归，落到静息基准 0.5
    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert len(smile) == 3
    assert smile[-1].end_value == 0.5


def _joy_then_sadness_profile() -> ExpressionProfileConfig:
    """JOY 驱动 mouth.smile、SADNESS 驱动 brow.height（不同 action）"""
    return ExpressionProfileConfig.model_validate(
        {
            "semantic_units": [
                {
                    "id": "嘴角上扬",
                    "targets": [{"action": "mouth.smile", "min_value": 0.9, "max_value": 0.9}],
                    "emotions": {"joy": 0.95},
                },
                {
                    "id": "皱眉",
                    "targets": [{"action": "brow.height", "min_value": 0.1, "max_value": 0.1}],
                    "emotions": {"sadness": 0.95},
                },
            ],
        }
    )


async def test_interrupt_runs_previous_neutral_priority_cleanup() -> None:
    """新表情硬打断旧表情后新表情立即驱动;旧参数由独立 restore 清理"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(
            transition_duration=0.0,
            hold_duration=10.0,
            neutral_transition_duration=0.0,
        ),
        _joy_then_sadness_profile(),
    )

    await controller.execute(emotion=EmotionKind.JOY)
    await asyncio.sleep(0)
    await controller.execute(emotion=EmotionKind.SADNESS)
    await _drain(controller)

    brow = [r for r in platform.requests if r.action_parameter_name == SemanticAction.BROW_HEIGHT.value]
    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert brow
    assert any(abs(r.end_value - 0.1) < 1e-6 and r.priority == EXPRESSION_AU_PRIORITY for r in brow)
    # 旧 smile 可能被 restore 拉回 0.5
    assert smile


async def test_oneshot_start_reentrant_interrupts() -> None:
    """通过 start() 连点:每次都返回 True,不因 is_running 丢弃"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(
            transition_duration=0.0,
            hold_duration=10.0,
            neutral_transition_duration=0.0,
        ),
        _joy_then_sadness_profile(),
    )
    ok1 = await controller.start(emotion=EmotionKind.JOY)
    ok2 = await controller.start(emotion=EmotionKind.SADNESS)
    ok3 = await controller.start(emotion=EmotionKind.JOY)
    ok4 = await controller.start(emotion=EmotionKind.SADNESS)
    ok5 = await controller.start(emotion=EmotionKind.JOY)
    assert all([ok1, ok2, ok3, ok4, ok5])
    await asyncio.sleep(0)
    await _drain(controller)
    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    # 至少有一次 JOY 驱动 smile;连点全部被接受(返回 True)
    assert smile


async def test_external_hold_release_runs_neutral_priority() -> None:
    """hold_duration=None: release_hold 发信号后 _drive 先 end 再后台 neutral_priority 回归"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(
            transition_duration=0.0,
            hold_duration=1.0,
            neutral_transition_duration=0.0,
        ),
        _joy_return_profile(),
    )
    await controller.execute(emotion=EmotionKind.JOY, hold_duration=None)
    session = controller.current_session
    assert session is not None
    for _ in range(5):
        await asyncio.sleep(0)
    smile_mid = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert smile_mid
    assert any(r.priority == EXPRESSION_AU_PRIORITY for r in smile_mid)
    # 协作释放:只发信号,不 await 恢复
    await controller.release_hold()
    # end 应很快触发(不依赖恢复完成)
    for _ in range(20):
        if session.ended:
            break
        await asyncio.sleep(0)
    assert session.ended
    await _drain(controller)
    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert any(r.end_value == 0.5 and r.priority == EXPRESSION_NEUTRAL_PRIORITY for r in smile)


async def test_end_fires_before_restore_completes() -> None:
    """end 锚点 = 开始回中性: fire end 时 neutral_priority 回归尚未完成"""
    platform = _ExpressionPlatform()

    # 让 neutral tween 慢一点,便于观察顺序
    original_tween = platform.tween_semantic

    restore_seen_before_end = {"value": False}
    ends: list[str] = []
    restore_started = asyncio.Event()
    restore_may_finish = asyncio.Event()

    async def slow_tween(requests):
        # EXPRESSION_NEUTRAL_PRIORITY = 回归段:卡住直到 end 已发
        if any(getattr(r, "priority", None) == EXPRESSION_NEUTRAL_PRIORITY for r in requests):
            restore_started.set()
            await restore_may_finish.wait()
        await original_tween(requests)

    platform.tween_semantic = slow_tween  # type: ignore[method-assign]

    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(
            transition_duration=0.0,
            hold_duration=0.0,
            neutral_transition_duration=0.2,
        ),
        _joy_return_profile(),
    )

    await controller.execute(emotion=EmotionKind.JOY, hold_duration=0.0)
    session = controller.current_session
    assert session is not None

    async def watch_end() -> None:
        await session.wait_ended()
        ends.append("end")
        restore_seen_before_end["value"] = True
        restore_may_finish.set()

    watcher = asyncio.create_task(watch_end())
    await _drain(controller)
    await watcher
    assert ends == ["end"]
    assert restore_seen_before_end["value"]
    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert any(r.end_value == 0.5 and r.priority == EXPRESSION_NEUTRAL_PRIORITY for r in smile)


async def test_drive_via_start_path_mimicking_mcp() -> None:
    """走 start()(=execute_controller=MCP 路径)而非 execute(),验证 _drive 仍跑恢复。"""
    platform = _ExpressionPlatform()
    controller = ExpressionController(
        _runtime(platform),
        "expression",
        ExpressionControllerSettings(
            transition_duration=0.0,
            hold_duration=1.0,
            neutral_transition_duration=0.0,
        ),
        _joy_return_profile(),
    )
    ok = await controller.start(emotion=EmotionKind.JOY, hold_duration=None)
    assert ok
    for _ in range(10):
        await asyncio.sleep(0)
    await controller.release_hold()
    await _drain(controller)
    smile = [r for r in platform.requests if r.action_parameter_name == SemanticAction.MOUTH_SMILE.value]
    assert smile, "没有任何 mouth.smile tween -> _drive 根本没跑"
    assert any(abs(r.end_value - 0.5) < 1e-6 and r.priority == 1 for r in smile), (
        f"无 neutral 回归段; got {[(r.end_value, r.priority) for r in smile]}"
    )

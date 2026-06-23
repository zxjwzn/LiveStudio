"""回归测试：验证本次重构涉及的生命周期、编排与风格改动

覆盖：
- Mixin 类级默认状态（不依赖子类 __init__ 声明）
- Mixin 模板方法：_do_initialize / _do_start / _do_stop
- Mixin 幂等守卫：重复调用安全
- AudioStreamSource 统一用 Mixin 标志（_mark_started / _mark_stopped）
- AudioStreamRouter._rebind_active_source 原子切换
- AnimationManager.initialize 幂等守卫
- easing 常量精度（_HALF_PI）
"""

# ruff: noqa: SLF001

from __future__ import annotations

import math
from typing import Any

import pytest

from livestudio.services.animations.manager import AnimationManager
from livestudio.services.audio_stream import (
    AudioSourceKind,
    AudioStreamRouter,
    AudioStreamRouterConfig,
)
from livestudio.services.audio_stream.base import AudioStreamSource
from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.utils.easing import _HALF_PI, Easing
from tests.conftest import _SemanticPlatform

# ──────────────────────────────────────────────
# 1. Mixin 默认状态 & 类级属性
# ──────────────────────────────────────────────


def test_mixin_default_state_without_explicit_init() -> None:
    """子类不声明 _initialized/_started 仍应返回 False。"""

    class _Bare(AsyncServiceLifecycleMixin):
        pass

    obj = _Bare()
    assert not obj.is_initialized
    assert not obj.is_started


def test_mixin_class_attrs_dont_bleed_across_instances() -> None:
    """一个实例修改标志不应影响另一个实例。"""

    class _Bare(AsyncServiceLifecycleMixin):
        pass

    a, b = _Bare(), _Bare()
    a._mark_initialized()
    assert a.is_initialized
    assert not b.is_initialized


# ──────────────────────────────────────────────
# 2. 模板方法 _do_initialize / _do_start / _do_stop
# ──────────────────────────────────────────────


class _TemplateService(AsyncServiceLifecycleMixin):
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def _do_initialize(self) -> None:
        self.calls.append("_do_initialize")

    async def _do_start(self) -> None:
        self.calls.append("_do_start")

    async def _do_stop(self) -> None:
        self.calls.append("_do_stop")


async def test_template_initialize_marks_initialized() -> None:
    svc = _TemplateService()
    await svc.initialize()
    assert svc.is_initialized
    assert "_do_initialize" in svc.calls


async def test_template_start_auto_initializes_and_marks_started() -> None:
    svc = _TemplateService()
    await svc.start()
    assert svc.is_initialized
    assert svc.is_started
    assert svc.calls == ["_do_initialize", "_do_start"]


async def test_template_stop_calls_do_stop_and_resets_flags() -> None:
    svc = _TemplateService()
    await svc.start()
    await svc.stop()
    assert not svc.is_started
    assert not svc.is_initialized
    assert "_do_stop" in svc.calls


async def test_template_start_rolls_back_on_failure() -> None:
    """_do_start 抛错时 stop() 应被调用，标志复位。"""

    class _FailStart(AsyncServiceLifecycleMixin):
        calls: list[str]

        def __init__(self) -> None:
            self.calls = []

        async def _do_initialize(self) -> None:
            self.calls.append("init")

        async def _do_start(self) -> None:
            self.calls.append("start")
            raise RuntimeError("start failed")

        async def _do_stop(self) -> None:
            self.calls.append("stop")

    svc = _FailStart()
    with pytest.raises(RuntimeError, match="start failed"):
        await svc.start()

    assert not svc.is_started
    assert not svc.is_initialized
    assert svc.calls == ["init", "start", "stop"]


# ──────────────────────────────────────────────
# 3. 幂等守卫
# ──────────────────────────────────────────────


async def test_initialize_is_idempotent() -> None:
    svc = _TemplateService()
    await svc.initialize()
    await svc.initialize()
    assert svc.calls.count("_do_initialize") == 1


async def test_start_is_idempotent() -> None:
    svc = _TemplateService()
    await svc.start()
    await svc.start()
    assert svc.calls.count("_do_start") == 1


async def test_stop_before_initialize_is_noop() -> None:
    svc = _TemplateService()
    await svc.stop()
    assert svc.calls == []


async def test_restart_calls_stop_then_start() -> None:
    svc = _TemplateService()
    await svc.start()
    svc.calls.clear()
    await svc.restart()
    assert "_do_stop" in svc.calls
    assert "_do_start" in svc.calls
    assert svc.is_started


async def test_restart_is_soft_keeps_initialized() -> None:
    """软重启不复位 _initialized：只有 stop 才是真正退出。"""

    svc = _TemplateService()
    await svc.start()
    assert svc.is_initialized
    await svc.restart()
    # restart 后仍处于已初始化 + 已启动；区别于 stop（会复位 _initialized）
    assert svc.is_initialized
    assert svc.is_started


async def test_restart_uses_do_restart_hook_not_stop_start() -> None:
    """重写 _do_restart 的服务，restart 应走该钩子而非默认 stop+start。"""

    class _SoftRestart(AsyncServiceLifecycleMixin):
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def _do_start(self) -> None:
            self.calls.append("start")

        async def _do_stop(self) -> None:
            self.calls.append("stop")

        async def _do_restart(self) -> None:
            self.calls.append("restart")

    svc = _SoftRestart()
    await svc.start()
    svc.calls.clear()
    await svc.restart()
    # 只调用了自定义软重启钩子，没有退化成 stop+start
    assert svc.calls == ["restart"]
    assert svc.is_started
    assert svc.is_initialized


async def test_restart_when_not_started_just_starts() -> None:
    """已初始化但未启动时 restart 等价一次 start，不调用 _do_restart。"""

    class _SoftRestart(AsyncServiceLifecycleMixin):
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def _do_start(self) -> None:
            self.calls.append("start")

        async def _do_stop(self) -> None:
            self.calls.append("stop")

        async def _do_restart(self) -> None:
            self.calls.append("restart")

    svc = _SoftRestart()
    await svc.initialize()
    await svc.restart()
    assert svc.calls == ["start"]
    assert svc.is_started


async def test_restart_rolls_back_to_stop_on_failure() -> None:
    """_do_restart 抛错时回滚到 stop（复位标志、释放资源）。"""

    class _FailRestart(AsyncServiceLifecycleMixin):
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def _do_start(self) -> None:
            self.calls.append("start")

        async def _do_stop(self) -> None:
            self.calls.append("stop")

        async def _do_restart(self) -> None:
            self.calls.append("restart")
            raise RuntimeError("restart failed")

    svc = _FailRestart()
    await svc.start()
    svc.calls.clear()
    with pytest.raises(RuntimeError, match="restart failed"):
        await svc.restart()
    assert svc.calls == ["restart", "stop"]
    assert not svc.is_started
    assert not svc.is_initialized


async def test_stop_resets_flags_even_when_do_stop_raises() -> None:
    """stop 是终止入口：即使 _do_stop 抛错也在 finally 复位标志。"""

    class _FailStop(AsyncServiceLifecycleMixin):
        async def _do_stop(self) -> None:
            raise RuntimeError("stop failed")

    svc = _FailStop()
    await svc.start()
    with pytest.raises(RuntimeError, match="stop failed"):
        await svc.stop()
    assert not svc.is_started
    assert not svc.is_initialized


# ──────────────────────────────────────────────
# 4. AudioStreamSource 统一 Mixin 标志
# ──────────────────────────────────────────────


class _MinimalSource(AudioStreamSource):
    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        self._mark_started()

    async def stop(self) -> None:
        self._mark_stopped()
        self._clear_subscriptions()


def test_audio_source_no_longer_has_set_started() -> None:
    """_set_started / _is_started 已删除，不应出现在实例上。"""
    src = _MinimalSource()
    assert not hasattr(src, "_set_started")
    assert not hasattr(src, "_is_started")


async def test_audio_source_is_started_uses_mixin_flag() -> None:
    src = _MinimalSource()
    assert not src.is_started
    await src.start()
    assert src.is_started
    await src.stop()
    assert not src.is_started


# ──────────────────────────────────────────────
# 5. AudioStreamRouter._rebind_active_source
# ──────────────────────────────────────────────


async def _noop() -> None:
    pass


async def _make_router() -> tuple[AudioStreamRouter, _MinimalSource, _MinimalSource]:
    router = AudioStreamRouter()
    config = AudioStreamRouterConfig()
    router.config_manager = type(  # type: ignore[assignment]
        "_CM",
        (),
        {"config": config, "save": lambda _self: _noop()},
    )()
    mic: _MinimalSource = _MinimalSource()
    tts: _MinimalSource = _MinimalSource()
    router._microphone_source = mic  # type: ignore[assignment]
    router._tts_source = tts  # type: ignore[assignment]
    router._sources = {AudioSourceKind.MICROPHONE: mic, AudioSourceKind.TTS: tts}
    router._active_source_kind = AudioSourceKind.MICROPHONE
    router._source_subscription = mic.subscribe(queue_maxsize=4)
    router._mark_initialized()
    return router, mic, tts


async def test_rebind_active_source_switches_subscription() -> None:
    router, mic, _ = await _make_router()
    old_sub = router._source_subscription
    assert old_sub is not None

    router._rebind_active_source(AudioSourceKind.TTS)

    assert router._active_source_kind is AudioSourceKind.TTS
    assert router._source_subscription is not old_sub
    assert str(old_sub.id) not in mic._subscriptions


async def test_rebind_active_source_updates_config() -> None:
    router, _, _ = await _make_router()
    router._rebind_active_source(AudioSourceKind.TTS)
    assert router.config.source is AudioSourceKind.TTS


# ──────────────────────────────────────────────
# 6. AnimationManager.initialize 幂等守卫
# ──────────────────────────────────────────────


async def test_animation_manager_initialize_idempotent(tmp_path: Any) -> None:
    manager = AnimationManager(template_root=tmp_path)
    manager.register_runtime(_SemanticPlatform())

    await manager.initialize()
    await manager.initialize()  # 二次调用

    assert manager.is_initialized


# ──────────────────────────────────────────────
# 7. easing 常量精度
# ──────────────────────────────────────────────


def test_half_pi_uses_math_pi() -> None:
    assert math.pi / 2 == _HALF_PI


def test_in_sine_at_one_equals_one_exactly() -> None:
    assert Easing.in_sine(1.0) == pytest.approx(1.0)


def test_out_sine_at_zero_equals_zero() -> None:
    assert Easing.out_sine(0.0) == pytest.approx(0.0, abs=1e-10)


def test_in_out_sine_at_half_equals_half() -> None:
    assert Easing.in_out_sine(0.5) == pytest.approx(0.5)

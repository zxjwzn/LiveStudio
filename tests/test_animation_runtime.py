"""测试动画运行流程能不能正常开始和结束"""

from __future__ import annotations

from typing import Any

import pytest

from livestudio.services.animations.controllers import (
    AnimationController,
    AnimationType,
    ControllerSettings,
)
from livestudio.services.animations.manager import AnimationManager
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from tests.conftest import _SemanticPlatform as _Platform
from tests.conftest import _TemplatePlayer


class _Controller(AnimationController[ControllerSettings]):
    def __init__(
        self,
        runtime: Any,
        name: str,
        config: ControllerSettings,
        *,
        animation_type: AnimationType = AnimationType.ONESHOT,
        fail_start: bool = False,
    ) -> None:
        super().__init__(runtime, name, config)
        self._animation_type = animation_type
        self.fail_start = fail_start
        self.cancel_calls = 0

    @property
    def animation_type(self) -> AnimationType:
        return self._animation_type

    async def start(self, **kwargs: object) -> bool:
        if self.fail_start:
            raise RuntimeError("start failed")
        return await super().start(**kwargs)

    async def cancel(self) -> None:
        self.cancel_calls += 1
        await super().cancel()

    async def run_cycle(self) -> None:
        await self._stop_event.wait()

    async def execute(self, **kwargs: object) -> None:
        _ = kwargs


async def test_runtime_stop_before_registering_controllers() -> None:
    platform = _Platform()
    runtime = PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )

    await runtime.stop()

    assert runtime.controllers == {}
    assert not runtime.is_started


def test_runtime_rejects_template_player_bound_to_another_platform() -> None:
    platform = _Platform()

    with pytest.raises(ValueError, match="模板播放器绑定的平台与运行时平台不一致"):
        PlatformAnimationRuntime(
            platform=platform,
            template_player=_TemplatePlayer(_Platform()),
        )


def test_runtime_rejects_controller_bound_to_another_runtime() -> None:
    source_platform = _Platform()
    source_runtime = PlatformAnimationRuntime(
        platform=source_platform,
        template_player=_TemplatePlayer(source_platform),
    )
    target_platform = _Platform()
    target_runtime = PlatformAnimationRuntime(
        platform=target_platform,
        template_player=_TemplatePlayer(target_platform),
    )
    controller = _Controller(source_runtime, "oneshot", ControllerSettings())

    with pytest.raises(ValueError, match="控制器绑定的运行时与目标运行时不一致"):
        target_runtime.register_controller(controller)


async def test_animation_manager_can_start_one_platform_runtime(
    tmp_path,
) -> None:
    manager = AnimationManager(template_root=tmp_path)
    left = _Platform("left")
    right = _Platform("right")
    manager.register_runtime(left)
    manager.register_runtime(right)

    await manager.start_runtime("left")

    assert manager.get_runtime("left").is_started
    assert not manager.get_runtime("right").is_started


async def test_runtime_rolls_back_started_idle_controllers_on_start_failure() -> None:
    platform = _Platform()
    runtime = PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )
    started = _Controller(
        runtime,
        "started",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    failed = _Controller(
        runtime,
        "failed",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
        fail_start=True,
    )
    runtime.register_controller(started)
    runtime.register_controller(failed)

    with pytest.raises(RuntimeError, match="start failed"):
        await runtime.start()

    assert not runtime.is_started
    assert not started.is_running
    assert started.cancel_calls == 1


async def test_reload_controllers_hot_swaps_when_started_individually() -> None:
    """reload_controllers 在 runtime 未 start 时也必须取消旧控制器并启动新控制器。

    回归：仪表盘用 start_controller 单独起控制器，绕过 runtime.start()，故 _started
    仍为 False。此前 reload_controllers 仅凭 _started 判定，会跳过停启——模型热切换时
    旧控制器残留为孤儿任务（持续注入参数、断开后向失效适配器报错），新控制器不启动
    （仪表盘开关显示已停止）。
    """

    platform = _Platform()
    runtime = PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )
    old = _Controller(
        runtime,
        "idle",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    runtime.register_controller(old)
    # 仪表盘单独起控制器：绕过 runtime.start()，_started 保持 False
    await runtime.start_controller("idle")
    assert old.is_running
    assert not runtime.is_started

    new = _Controller(
        runtime,
        "idle",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    await runtime.reload_controllers([new])

    # 旧控制器被取消（无孤儿任务），新控制器已启动，runtime 服务态保持未 start
    assert old.cancel_calls == 1
    assert not old.is_running
    assert new.is_running
    assert not runtime.is_started


async def test_reload_controllers_preserves_started_flag_when_bulk_started() -> None:
    """runtime 已 start（批量起控制器）时，reload_controllers 保持 _started=True 并热替换。"""

    platform = _Platform()
    runtime = PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )
    old = _Controller(
        runtime,
        "idle",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    runtime.register_controller(old)
    await runtime.start()
    assert runtime.is_started
    assert old.is_running

    new = _Controller(
        runtime,
        "idle",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    await runtime.reload_controllers([new])

    assert old.cancel_calls == 1
    assert not old.is_running
    assert new.is_running
    assert runtime.is_started


async def test_reload_controllers_preserves_per_controller_running_state() -> None:
    """换模型热替换时保留各控制器运行态:替换前在跑的重启,关掉的不重启。

    回归:此前 reload_controllers 走 _do_start(启动全部 idle),会把用户单独关掉的
    控制器重新打开。改为按名匹配后,关掉的保持关闭。
    """

    platform = _Platform()
    runtime = PlatformAnimationRuntime(
        platform=platform,
        template_player=_TemplatePlayer(platform),
    )
    blink = _Controller(
        runtime,
        "blink",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    breathing = _Controller(
        runtime,
        "breathing",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    runtime.register_controller(blink)
    runtime.register_controller(breathing)
    # 仪表盘单独起:blink 开、breathing 关
    await runtime.start_controller("blink")
    assert blink.is_running
    assert not breathing.is_running

    new_blink = _Controller(
        runtime,
        "blink",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    new_breathing = _Controller(
        runtime,
        "breathing",
        ControllerSettings(),
        animation_type=AnimationType.IDLE,
    )
    await runtime.reload_controllers([new_blink, new_breathing])

    # 旧控制器被取消(无孤儿);新 blink 重启(之前在跑),新 breathing 不启动(之前关掉)
    assert blink.cancel_calls == 1
    assert new_blink.is_running
    assert not new_breathing.is_running
    assert not runtime.is_started

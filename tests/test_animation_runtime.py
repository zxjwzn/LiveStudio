"""PlatformAnimationRuntime lifecycle tests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import pytest

from livestudio.services.animations.controllers import (
    AnimationController,
    AnimationType,
    ControllerSettings,
)
from livestudio.services.animations.manager import AnimationManager
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.animations.templates import (
    AnimationTemplatePlayer,
    LoadedTemplateInfo,
)
from livestudio.services.platforms import PlatformService
from livestudio.tween import ControlledParameterState, ParameterTweenEngine


class _TemplatePlayer(AnimationTemplatePlayer):
    def __init__(self, platform: PlatformService) -> None:
        self._platform = platform

    async def load(self) -> None:
        pass

    async def reload(self) -> None:
        pass

    def list_loaded_templates(self) -> list[LoadedTemplateInfo]:
        return []


class _Platform(PlatformService):
    def __init__(self, name: str = "test") -> None:
        self._name = name
        self._tween = ParameterTweenEngine(self.send_parameter_states)

    @property
    def name(self) -> str:
        return self._name

    @property
    def tween(self) -> ParameterTweenEngine:
        return self._tween

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"] = "set",
    ) -> None:
        _ = states, mode


class _Controller(AnimationController[ControllerSettings]):
    def __init__(
        self,
        runtime: PlatformAnimationRuntime,
        name: str,
        config: ControllerSettings,
        *,
        animation_type: AnimationType = AnimationType.ONESHOT,
        fail_start: bool = False,
    ) -> None:
        super().__init__(runtime, name, config)
        self._animation_type = animation_type
        self.fail_start = fail_start
        self.stop_without_wait_calls = 0

    @property
    def animation_type(self) -> AnimationType:
        return self._animation_type

    async def start(self, **kwargs: object) -> bool:
        if self.fail_start:
            raise RuntimeError("start failed")
        return await super().start(**kwargs)

    async def stop_without_wait(self) -> None:
        self.stop_without_wait_calls += 1
        await super().stop_without_wait()

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
    assert started.stop_without_wait_calls == 1

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
        self._tween = ParameterTweenEngine(self._send)

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

    async def _send(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        _ = states, mode


class _Controller(AnimationController[ControllerSettings]):
    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.ONESHOT

    async def run_cycle(self) -> None:
        pass

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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_load(self: AnimationTemplatePlayer) -> None:
        self._loaded = True

    monkeypatch.setattr(AnimationTemplatePlayer, "load", no_load)
    manager = AnimationManager(template_root=tmp_path)
    left = _Platform("left")
    right = _Platform("right")
    manager.register_runtime(left)
    manager.register_runtime(right)

    await manager.start_runtime("left")

    assert manager.get_runtime("left").is_started
    assert not manager.get_runtime("right").is_started

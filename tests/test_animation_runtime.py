"""PlatformAnimationRuntime lifecycle tests."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.animations.templates import (
    AnimationTemplatePlayer,
    LoadedTemplateInfo,
)
from livestudio.services.platforms import PlatformService
from livestudio.tween import ControlledParameterState, ParameterTweenEngine


class _TemplatePlayer(AnimationTemplatePlayer):
    def __init__(self) -> None:
        pass

    async def load(self) -> None:
        pass

    async def reload(self) -> None:
        pass

    def list_loaded_templates(self) -> list[LoadedTemplateInfo]:
        return []


class _Platform(PlatformService):
    def __init__(self) -> None:
        self._tween = ParameterTweenEngine(self._send)

    @property
    def name(self) -> str:
        return "test"

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


async def test_runtime_stop_before_registering_controllers() -> None:
    runtime = PlatformAnimationRuntime(
        platform=_Platform(),
        template_player=_TemplatePlayer(),
    )

    await runtime.stop()

    assert runtime.controllers == {}
    assert not runtime.is_started

"""共享 pytest 测试准备项"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from livestudio.services.animations.templates import (
    AnimationTemplatePlayer,
    LoadedTemplateInfo,
)
from livestudio.services.platforms import PlatformService
from livestudio.services.semantic_actions import SemanticTweenRequest
from livestudio.services.tween import ControlledParameterState, ParameterTweenEngine


class _SenderRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[Literal["set", "add"], list[ControlledParameterState]]] = []

    async def __call__(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"],
    ) -> None:
        self.calls.append((mode, list(states)))


class _TemplatePlayer(AnimationTemplatePlayer):
    def __init__(self, platform: PlatformService) -> None:
        self._platform = platform

    async def load(self) -> None:
        pass

    async def reload(self) -> None:
        pass

    def list_loaded_templates(self) -> list[LoadedTemplateInfo]:
        return []


class _SemanticPlatform(PlatformService):
    def __init__(self, name: str = "semantic-test") -> None:
        self._name = name
        self.requests: list[SemanticTweenRequest] = []
        self.semantic_values: dict[str, float] = {}
        self._tween = ParameterTweenEngine(self.send_parameter_states)

    @property
    def name(self) -> str:
        return self._name

    @property
    def tween(self) -> ParameterTweenEngine:
        return self._tween

    async def tween_semantic(self, requests: Iterable[Any]) -> None:
        self.requests.extend(requests)

    async def get_semantic_value(self, action: str) -> float | None:
        return self.semantic_values.get(action)

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"] = "set",
    ) -> None:
        _ = states, mode

"""测试平台服务语义动作入口"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import pytest

from livestudio.services.platforms import PlatformService
from livestudio.services.semantic_actions import SemanticTweenRequest
from livestudio.services.tween import ControlledParameterState, ParameterTweenEngine


class _NoSemanticPlatform(PlatformService):
    def __init__(self) -> None:
        self._tween = ParameterTweenEngine(self.send_parameter_states)

    @property
    def name(self) -> str:
        return "no-semantic"

    @property
    def tween(self) -> ParameterTweenEngine:
        return self._tween

    async def send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"] = "set",
    ) -> None:
        _ = states, mode

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


async def test_platform_service_reports_missing_semantic_adapter() -> None:
    platform = _NoSemanticPlatform()

    with pytest.raises(NotImplementedError, match="未实现语义动作适配器"):
        await platform.tween_semantic(
            [
                SemanticTweenRequest(
                    action_parameter_name="mouth.open",
                    end_value=0.5,
                    duration=0.1,
                    easing="linear",
                ),
            ],
        )

    assert await platform.get_semantic_value("mouth.open") is None

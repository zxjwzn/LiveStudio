"""测试通用动作动画模板"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import ValidationError

from livestudio.services.animations.templates import AnimationTemplatePlayer
from livestudio.services.animations.templates.models import AnimationTemplate
from livestudio.services.platforms import PlatformService
from livestudio.services.platforms.vtubestudio import (
    default_vtube_studio_parameter_specs,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.semantic_actions import SemanticAction, SemanticActionAdapter
from livestudio.services.tween import ControlledParameterState, ParameterTweenEngine
from tests.conftest import _SemanticPlatform


class _AdapterBackedSemanticPlatform(_SemanticPlatform):
    def __init__(self) -> None:
        super().__init__("semantic-template-adapter-test")
        self.sent_states: list[ControlledParameterState] = []
        self._tween = ParameterTweenEngine(self.send_parameter_states)
        self._semantic_adapter = SemanticActionAdapter(
            default_vtube_studio_semantic_profile(),
            parameter_specs=default_vtube_studio_parameter_specs(),
            engine=self._tween,
        )

    @property
    def semantic_adapter(self) -> SemanticActionAdapter:
        return self._semantic_adapter

    async def tween_semantic(
        self,
        requests: Iterable[Any],
    ) -> None:
        await PlatformService.tween_semantic(self, requests)

    async def send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"] = "set",
    ) -> None:
        _ = mode
        self.sent_states.extend(states)


def _template() -> AnimationTemplate:
    return AnimationTemplate.model_validate(
        {
            "name": "smile",
            "data": {
                "params": [
                    {
                        "name": "amount",
                        "default": 0.6,
                    },
                ],
                "actions": [
                    {
                        "parameter": SemanticAction.MOUTH_SMILE.value,
                        "from": 0.0,
                        "to": {"expr": "amount"},
                        "duration": 0.2,
                        "easing": "in_out_sine",
                    },
                ],
            },
        },
    )


def test_template_render_outputs_semantic_actions(tmp_path: Path) -> None:
    player = AnimationTemplatePlayer(
        platform=_SemanticPlatform("semantic-template-test"),
        template_dir=tmp_path,
    )

    playback = player.render(_template())

    assert len(playback.actions) == 1
    request = playback.actions[0]
    assert request.action_parameter_name == SemanticAction.MOUTH_SMILE.value
    assert request.end_value == 0.6
    assert request.start_value == 0.0


async def test_template_play_uses_platform_semantic_tween(tmp_path: Path) -> None:
    platform = _SemanticPlatform("semantic-template-test")
    template_path = tmp_path / "smile.jsonc"
    template_path.write_text(
        """
        {
          name: "smile",
          data: {
            actions: [
              {
                parameter: "mouth.open",
                to: 0.4,
                duration: 0.1
              }
            ]
          }
        }
        """,
        encoding="utf-8",
    )
    player = AnimationTemplatePlayer(platform=platform, template_dir=tmp_path)

    await player.play_template("smile")

    assert len(platform.requests) == 1
    assert platform.requests[0].action_parameter_name == SemanticAction.MOUTH_OPEN.value


async def test_template_play_is_compatible_with_semantic_adapter(
    tmp_path: Path,
) -> None:
    platform = _AdapterBackedSemanticPlatform()
    template_path = tmp_path / "mouth_open.jsonc"
    template_path.write_text(
        """
        {
          name: "mouth_open",
          data: {
            params: [
              { name: "amount", default: 0.4 }
            ],
            variables: {
              target: { expr: "amount + 0.2" }
            },
            actions: [
              {
                parameter: "mouth.open",
                to: { expr: "target" },
                duration: 0
              }
            ]
          }
        }
        """,
        encoding="utf-8",
    )
    player = AnimationTemplatePlayer(platform=platform, template_dir=tmp_path)

    playback = await player.play_template("mouth_open")

    assert playback.context["target"] == pytest.approx(0.6)
    assert len(playback.actions) == 1
    assert playback.actions[0].action_parameter_name == SemanticAction.MOUTH_OPEN.value
    assert playback.actions[0].end_value == pytest.approx(0.6)
    assert len(platform.sent_states) == 1
    assert platform.sent_states[0].name == "MouthOpen"
    assert platform.sent_states[0].value == pytest.approx(0.6)


def test_template_rejects_platform_parameter_names() -> None:
    with pytest.raises(ValidationError):
        AnimationTemplate.model_validate(
            {
                "name": "raw-vts",
                "data": {
                    "actions": [
                        {
                            "parameter": "MouthOpen",
                            "to": 0.4,
                        },
                    ],
                },
            },
        )

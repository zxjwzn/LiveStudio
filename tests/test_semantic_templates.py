"""测试通用动作动画模板"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from livestudio.services.animations.templates import AnimationTemplatePlayer
from livestudio.services.animations.templates.models import AnimationTemplate
from livestudio.services.semantic_actions.models import SemanticAction
from tests.conftest import _SemanticPlatform


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
    assert request.targets[0].action == SemanticAction.MOUTH_SMILE.value
    assert request.targets[0].value == 0.6
    assert request.targets[0].start_value == 0.0


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
    assert platform.requests[0].targets[0].action == SemanticAction.MOUTH_OPEN.value


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

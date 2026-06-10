"""测试 main.py 里 AU 命令的小工具"""

from __future__ import annotations

import pytest

from livestudio.services.expressions import EmotionKind
from main import _build_emotion_request, _build_parser


def test_au_cli_builds_emotion_request() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--au-preview",
            "--emotion",
            "joy=0.8",
            "--intensity",
            "0.6",
            "--randomness",
            "0",
        ],
    )

    request = _build_emotion_request(args)

    assert request.emotions == {EmotionKind.JOY: 0.8}
    assert request.intensity == 0.6
    assert request.randomness == 0.0


def test_au_cli_rejects_multiple_emotions() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--au-preview",
            "--emotion",
            "joy=0.8",
            "--emotion",
            "sadness=0.2",
        ],
    )

    with pytest.raises(ValueError, match="只能包含一个正向情绪强度"):
        _build_emotion_request(args)

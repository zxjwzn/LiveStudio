"""TTS 全局连接槽与 make_engine"""

from __future__ import annotations

import pytest

from livestudio.services.animations.controllers.config import TTSpeakControllerSettings
from livestudio.services.audio_stream.sources.tts.config import TTSAudioStreamConfig
from livestudio.services.audio_stream.sources.tts.engines import (
    FishAudioConnectionConfig,
    FishAudioEngine,
    connection_for_kind,
    make_engine,
)


def test_global_tts_config_has_fish_slot() -> None:
    cfg = TTSAudioStreamConfig()
    assert isinstance(cfg.fish_audio, FishAudioConnectionConfig)


def test_migrate_legacy_engine_block() -> None:
    cfg = TTSAudioStreamConfig.model_validate(
        {
            "engine": {
                "kind": "fish_audio",
                "api_key": "secret",
                "endpoint": "https://example.com/tts",
                "model": "s1",
                "reference_id": "x",
            },
            "samplerate": 24000,
            "channels": 1,
        },
    )
    assert cfg.fish_audio.api_key == "secret"
    assert cfg.fish_audio.endpoint == "https://example.com/tts"


def test_connection_for_kind_fish() -> None:
    conn = FishAudioConnectionConfig(api_key="k")
    assert connection_for_kind(fish_audio=conn, kind="fish_audio") is conn


def test_connection_for_kind_unknown() -> None:
    with pytest.raises(RuntimeError, match="未知 TTS"):
        connection_for_kind(fish_audio=FishAudioConnectionConfig(), kind="azure")


def test_make_engine_fish() -> None:
    engine = make_engine(FishAudioConnectionConfig(api_key="k"), sample_rate=24000, channels=1)
    assert isinstance(engine, FishAudioEngine)


def test_tts_speak_settings_flat() -> None:
    s = TTSpeakControllerSettings(
        kind="fish_audio",
        model="s1",
        reference_id="v",
        extra={"speed": 1.5},
    )
    opts = s.as_speak_opts()
    assert opts["kind"] == "fish_audio"
    assert opts["model"] == "s1"
    assert opts["reference_id"] == "v"
    assert opts["extra"]["speed"] == 1.5

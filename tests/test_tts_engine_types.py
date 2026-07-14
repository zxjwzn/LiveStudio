"""TTS 供应商注册表 + make_engine + speak 配置"""

from __future__ import annotations

import pytest

from livestudio.services.animations.controllers.config import TTSpeakControllerSettings
from livestudio.services.audio_stream.sources.tts.config import TTSAudioStreamConfig
from livestudio.services.audio_stream.sources.tts.engines import (
    FishAudioConnectionConfig,
    FishAudioEngine,
    FishAudioSpeakConfig,
    TTS_ENGINES,
    make_engine,
)


def test_global_tts_config_has_fish_slot_with_global_params() -> None:
    cfg = TTSAudioStreamConfig()
    assert isinstance(cfg.fish_audio, FishAudioConnectionConfig)
    assert cfg.fish_audio.model == "s2.1-pro-free"
    assert cfg.fish_audio.latency == "balanced"
    assert cfg.fish_audio.speed == 1.0


def test_make_engine_fish() -> None:
    engine = make_engine(
        "fish_audio",
        FishAudioConnectionConfig(api_key="k"),
        sample_rate=24000,
        channels=1,
    )
    assert isinstance(engine, FishAudioEngine)


def test_make_engine_unknown_kind() -> None:
    with pytest.raises(TypeError, match="未知 TTS"):
        make_engine("azure", FishAudioConnectionConfig(), sample_rate=24000, channels=1)


def test_tts_engines_registry_has_fish() -> None:
    assert TTS_ENGINES["fish_audio"] is FishAudioEngine


def test_tts_speak_settings_structured() -> None:
    s = TTSpeakControllerSettings(
        kind="fish_audio",
        fish_audio=FishAudioSpeakConfig(reference_id="v"),
    )
    req = s.as_speak_request()
    assert req.kind == "fish_audio"
    assert req.fish_audio.reference_id == "v"
    assert set(FishAudioSpeakConfig.model_fields) == {"reference_id"}


def test_tts_speak_settings_rejects_unknown_fields() -> None:
    with pytest.raises(Exception):
        TTSpeakControllerSettings.model_validate({
            "kind": "fish_audio",
            "fish_audio": {
                "reference_id": "v",
                "model": "s1",
                "latency": "low",
                "speed": 1.5,
            },
        })

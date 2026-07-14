"""TTS 供应商注册表 + make_engine + speak 配置"""

from __future__ import annotations

import pytest

from livestudio.services.animations.controllers.config import TTSpeakControllerSettings
from livestudio.services.audio_stream.sources.tts.config import TTSAudioStreamConfig
from livestudio.services.audio_stream.sources.tts.engines import (
    TTS_ENGINES,
    FishAudioConnectionConfig,
    FishAudioEngine,
    FishAudioSpeakConfig,
    TtsSpeakRequest,
    make_engine,
)


def test_global_tts_config_has_fish_slot() -> None:
    cfg = TTSAudioStreamConfig()
    assert isinstance(cfg.fish_audio, FishAudioConnectionConfig)


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
        fish_audio=FishAudioSpeakConfig(model="s1", reference_id="v", speed=1.5),
    )
    request = s.create_speak_request(text="spoken", subtitle="displayed")
    assert isinstance(request, TtsSpeakRequest)
    assert request.kind == "fish_audio"
    assert request.text == "spoken"
    assert request.subtitle == "displayed"
    assert request.fish_audio.model == "s1"
    assert request.fish_audio.reference_id == "v"
    assert request.fish_audio.speed == 1.5
    assert request.fish_audio.latency == "balanced"


def test_tts_speak_settings_migrates_flat_fields() -> None:
    """旧配置顶层 model/reference_id/extra -> fish_audio 子对象(迁移垫片)。

    用 model_validate(dict) 模拟真实配置加载(旧字段非声明字段,经 before-validator 消化)。
    """
    s = TTSpeakControllerSettings.model_validate(
        {
            "kind": "fish_audio",
            "model": "s1",
            "reference_id": "v",
            "extra": {"speed": 1.5, "latency": "low"},
        }
    )
    assert s.fish_audio.model == "s1"
    assert s.fish_audio.reference_id == "v"
    assert s.fish_audio.speed == 1.5
    assert s.fish_audio.latency == "low"
    request = s.create_speak_request(text="text", subtitle="subtitle")
    assert request.fish_audio.model == "s1"
    assert request.fish_audio.speed == 1.5
    assert request.fish_audio.latency == "low"

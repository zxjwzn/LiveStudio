"""GUI 常量"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from livestudio.services.audio_stream.models import AudioSourceKind

ASSETS_DIR: Final[Path] = Path(__file__).resolve().parent / "assets"
APP_ICON_PATH: Final[Path] = ASSETS_DIR / "app_icon.svg"

LOG_MAX_ROWS: Final[int] = 2000
LOG_LEVELS: Final[tuple[str, ...]] = ("DEBUG", "INFO", "WARNING", "ERROR")
LOG_LEVEL_COLOR_DARK: Final[dict[str, str]] = {
    "DEBUG": "#94A3B8",
    "INFO": "#38BDF8",
    "WARNING": "#FBBF24",
    "ERROR": "#F87171",
}
LOG_LEVEL_COLOR_LIGHT: Final[dict[str, str]] = {
    "DEBUG": "#475569",
    "INFO": "#0284C7",
    "WARNING": "#B45309",
    "ERROR": "#DC2626",
}

AUDIO_METER_BAR_GAP: Final[int] = 6
AUDIO_METER_LABEL_WIDTH: Final[int] = 48
AUDIO_METER_TRACK_DARK: Final[str] = "#1E293B"
AUDIO_METER_TRACK_LIGHT: Final[str] = "#E2E8F0"
AUDIO_METER_TEXT_DARK: Final[str] = "#F8FAFC"
AUDIO_METER_TEXT_LIGHT: Final[str] = "#0F172A"

AUDIO_METER_INTERVAL_MS: Final[int] = 12
AUDIO_SOURCE_LABEL: Final[dict[AudioSourceKind, str]] = {
    AudioSourceKind.MICROPHONE: "麦克风",
    AudioSourceKind.TTS: "TTS",
}

# TTS 供应商展示名(键为 TtsProviderKind 值,即 TTSpeakControllerSettings 的并列字段名);
# 新增供应商在此补一条,未命中者回退为 kind 原文。
TTS_PROVIDER_LABEL: Final[dict[str, str]] = {
    "fish_audio": "Fish Audio",
}

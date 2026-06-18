"""实时音频电平条组件。

显示 rms / peak 两条进度条，数值 0..1。仪表盘与音频流页复用。
由调用方订阅 state.audio_level 后调用 update_level 刷新。
"""

from __future__ import annotations

import flet as ft

from ..core.theme import PALETTE
from ..core.view_models import AudioLevelVM, AudioSourceKind

_SOURCE_LABELS: dict[AudioSourceKind, str] = {
    AudioSourceKind.MICROPHONE: "麦克风",
    AudioSourceKind.TTS: "TTS",
}


class AudioMeter(ft.Column):
    """rms / peak 双条电平表。"""

    def __init__(self, *, compact: bool = False) -> None:
        self._compact = compact
        self._source_text = ft.Text("音频未启动", size=13, color=PALETTE.text_muted)
        self._rms_bar = ft.ProgressBar(
            value=0.0,
            bgcolor=PALETTE.surface_alt,
            color=PALETTE.primary,
            bar_height=10,
            border_radius=ft.border_radius.all(5),
        )
        self._peak_bar = ft.ProgressBar(
            value=0.0,
            bgcolor=PALETTE.surface_alt,
            color=PALETTE.accent_audio,
            bar_height=6,
            border_radius=ft.border_radius.all(3),
        )
        self._rms_label = ft.Text("rms 0.00", size=11, color=PALETTE.text_muted)
        self._peak_label = ft.Text("peak 0.00", size=11, color=PALETTE.text_muted)
        super().__init__(
            spacing=6,
            controls=[
                self._source_text,
                ft.Row([ft.Container(self._rms_bar, expand=True), self._rms_label], spacing=8),
                ft.Row([ft.Container(self._peak_bar, expand=True), self._peak_label], spacing=8),
            ],
        )

    def update_level(self, level: AudioLevelVM) -> None:
        """根据电平快照刷新显示（不主动 update，由调用方决定）。"""

        self._rms_bar.value = _clamp(level.rms)
        self._peak_bar.value = _clamp(level.peak)
        self._rms_label.value = f"rms {level.rms:.2f}"
        self._peak_label.value = f"peak {level.peak:.2f}"
        if level.active:
            source = _SOURCE_LABELS.get(level.source, level.source.value)
            self._source_text.value = f"源: {source}"
            self._source_text.color = PALETTE.text
        else:
            self._source_text.value = "音频未启动"
            self._source_text.color = PALETTE.text_muted


def _clamp(value: float) -> float:
    """把电平限制到 ProgressBar 可接受的 0..1。"""

    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value

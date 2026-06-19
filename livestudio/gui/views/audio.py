"""音频流页（P5）。

- 实时电平：大号 ``AudioMeter``，订阅 ``state.audio_level``。
- 音频源：单选 + [切换] -> ``bridge.switch_audio_source(kind)``；切换中按钮禁用。
  失败回滚由后端 ``AudioStreamRouter`` 保证，UI 仅反映 ``state.audio_source`` 变化。
"""

from __future__ import annotations

import flet as ft

from ..components.audio_meter import AudioMeter
from ..components.section import Section
from ..core.base_view import BaseView
from ..core.theme import PALETTE
from ..core.view_models import AudioLevelVM, AudioSourceKind

_SOURCE_LABELS: dict[AudioSourceKind, str] = {
    AudioSourceKind.MICROPHONE: "麦克风",
    AudioSourceKind.TTS: "TTS",
}


class AudioView(BaseView):
    """音频流视图。"""

    def build_content(self) -> ft.Control:
        # 选中草稿：用户在 UI 上选了什么；与 state.audio_source 解耦，确认时才切换
        self._draft = AudioSourceKind.MICROPHONE
        self._switching = False

        # 实时电平卡
        self._audio_meter = AudioMeter()
        meter_card = Section("实时电平", self._audio_meter)

        # 音频源单选
        self._source_radio = ft.RadioGroup(
            value=AudioSourceKind.MICROPHONE.value,
            on_change=self._on_radio_change,
            content=ft.Column(
                spacing=8,
                controls=[
                    self._radio_row(AudioSourceKind.MICROPHONE, "麦克风", "系统输入设备"),
                    self._radio_row(AudioSourceKind.TTS, "TTS", "PCM 16kHz / 16bit / mono"),
                ],
            ),
        )

        self._active_hint = ft.Text("当前: 麦克风", size=12, color=PALETTE.text_muted)
        self._switch_button = ft.FilledButton(
            text="切换为选中源",
            icon=ft.Icons.SWAP_HORIZ,
            on_click=self._on_switch_click,
            style=ft.ButtonStyle(
                bgcolor=PALETTE.primary,
                color=PALETTE.on_primary,
            ),
        )
        source_card = Section(
            "音频源",
            ft.Column(
                spacing=14,
                controls=[
                    self._source_radio,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[self._active_hint, self._switch_button],
                    ),
                ],
            ),
        )

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                ft.Text("音频流", size=22, weight=ft.FontWeight.W_600, color=PALETTE.text),
                meter_card,
                source_card,
            ],
        )

    # —— 单选行 ——
    def _radio_row(self, kind: AudioSourceKind, label: str, hint: str) -> ft.Control:
        return ft.Row(
            spacing=8,
            controls=[
                ft.Radio(value=kind.value),
                ft.Column(
                    spacing=0,
                    controls=[
                        ft.Text(label, size=14, color=PALETTE.text),
                        ft.Text(hint, size=11, color=PALETTE.text_muted),
                    ],
                ),
            ],
        )

    # —— 订阅 ——
    def bind(self) -> None:
        self.watch(self.state.audio_level, self._on_audio_level)
        self.watch(self.state.audio_source, self._on_audio_source)

    def _on_audio_level(self, level: AudioLevelVM) -> None:
        self._audio_meter.update_level(level)
        self.safe_update()

    def _on_audio_source(self, kind: AudioSourceKind) -> None:
        # 后端确认切换后：单选同步、解禁按钮、刷新文案
        self._draft = kind
        self._switching = False
        self._source_radio.value = kind.value
        self._active_hint.value = f"当前: {_SOURCE_LABELS.get(kind, kind.value)}"
        self._update_switch_button()
        self.safe_update()

    # —— 交互 ——
    def _on_radio_change(self, e: ft.ControlEvent) -> None:
        try:
            self._draft = AudioSourceKind(e.control.value)
        except ValueError:
            return
        self._update_switch_button()
        self.safe_update()

    def _on_switch_click(self, _e: ft.ControlEvent) -> None:
        bridge = self.ctx.bridge
        if bridge is None or self._switching:
            return
        if self._draft == self.state.audio_source.value:
            return
        self._switching = True
        self._update_switch_button()
        self.safe_update()
        target = self._draft
        self.run_intent(lambda: bridge.switch_audio_source(target))

    def _update_switch_button(self) -> None:
        """根据是否切换中/草稿是否与当前一致，控制按钮可用与文案。"""

        if self._switching:
            self._switch_button.text = "切换中…"
            self._switch_button.disabled = True
            return
        if self._draft == self.state.audio_source.value:
            self._switch_button.text = "已是当前源"
            self._switch_button.disabled = True
        else:
            self._switch_button.text = "切换为选中源"
            self._switch_button.disabled = False

"""音频流页（P5）。

- 实时电平：大号 ``AudioMeter``，订阅 ``state.audio_level``。
- 音频源：单选 + [切换] -> ``bridge.switch_audio_source(kind)``；切换中按钮禁用。
  失败回滚由后端 ``AudioStreamRouter`` 保证，UI 仅反映 ``state.audio_source`` 变化。
"""

from __future__ import annotations

import flet as ft

from livestudio.utils.log import logger

from ..components.audio_meter import AudioMeter
from ..components.config_editor import ConfigEditor
from ..components.section import Section
from ..core.base_view import BaseView
from ..core.mount_aware import updates_ui
from ..core.theme import PALETTE, TYPE
from ..core.view_models import AudioLevelVM, AudioSourceKind, audio_source_label


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

        self._active_hint = ft.Text("当前: 麦克风", size=TYPE.caption, color=PALETTE.text_muted)
        self._switch_button = ft.FilledButton(
            text="切换为选中源",
            icon=ft.Icons.SWAP_HORIZ,
            on_click=self._on_switch_click,
            style=ft.ButtonStyle(
                bgcolor=PALETTE.primary,
                color=PALETTE.on_primary,
            ),
        )
        # 重启音源按钮：紧邻切换按钮，就地重启当前输入源使已保存的配置（如换设备）生效
        self._restart_button = ft.OutlinedButton(
            text="重启音源",
            icon=ft.Icons.RESTART_ALT,
            tooltip="就地重启当前输入源，应用已保存的配置（如更换设备）",
            on_click=self._on_restart_click,
        )
        source_card = Section(
            "音频源",
            ft.Column(
                spacing=14,
                controls=[
                    self._source_radio,
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            self._active_hint,
                            ft.Row(spacing=8, controls=[self._restart_button, self._switch_button]),
                        ],
                    ),
                ],
            ),
        )

        # 麦克风配置卡（数据驱动：bridge 反射 Pydantic 配置 -> ConfigEditor）
        # 改动暂存内存；保存按钮落盘；重启音源按钮（在「音频源」卡）重启输入源使其生效。
        self._config_dirty = False
        self._config_hint = ft.Text("已保存", size=TYPE.caption, color=PALETTE.text_muted)
        self._save_button = ft.FilledButton(
            text="保存",
            icon=ft.Icons.SAVE_OUTLINED,
            disabled=True,
            on_click=self._on_save_click,
            style=ft.ButtonStyle(bgcolor=PALETTE.primary, color=PALETTE.on_primary),
        )
        self._config_actions = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self._config_hint, self._save_button],
        )
        self._mic_config_body = ft.Column(
            spacing=12,
            tight=True,
            controls=[ft.Text("麦克风配置不可用", size=TYPE.caption, color=PALETTE.text_muted)],
        )
        config_card = Section("麦克风配置", self._mic_config_body)

        return ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=16,
            controls=[
                ft.Text("音频流", size=TYPE.title, weight=ft.FontWeight.W_600, color=PALETTE.text),
                meter_card,
                source_card,
                config_card,
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
                        ft.Text(label, size=TYPE.body_lg, color=PALETTE.text),
                        ft.Text(hint, size=TYPE.small, color=PALETTE.text_muted),
                    ],
                ),
            ],
        )

    # —— 订阅 ——
    def bind(self) -> None:
        self.watch(self.state.audio_level, self._on_audio_level)
        self.watch(self.state.audio_source, self._on_audio_source)
        self._build_mic_config()

    def _build_mic_config(self) -> None:
        """从 bridge 反射麦克风配置并渲染为 ConfigEditor（含动态设备下拉）。"""

        bridge = self.ctx.bridge
        if bridge is None:
            return
        section = bridge.microphone_config_section()
        editor = ConfigEditor(
            list(section.fields),
            on_change=self._on_config_change,
            choices_registry=bridge.choices,
            scheduler=self.run_intent,
        )
        self._mic_config_body.controls = [editor, self._config_actions]
        self._set_dirty(False)
        self.safe_update()

    def _on_config_change(self, path: str, value: object) -> None:
        # 改动仅暂存到内存配置；显式「保存」才落盘，「重启音源」才让其对运行中的流生效。
        bridge = self.ctx.bridge
        if bridge is None:
            return
        bridge.stage_microphone_field(path, value)
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        """标记是否有未保存改动，联动保存按钮可用态与提示。"""

        self._config_dirty = dirty
        self._save_button.disabled = not dirty
        self._config_hint.value = "有未保存改动" if dirty else "已保存"
        self._config_hint.color = PALETTE.warning if dirty else PALETTE.text_muted
        self.safe_update()

    def _on_save_click(self, _e: ft.ControlEvent) -> None:
        bridge = self.ctx.bridge
        if bridge is None or not self._config_dirty:
            return

        async def _save() -> None:
            ok = await bridge.save_microphone_config()
            if ok:
                self._set_dirty(False)
            self._config_hint.value = "已保存" if ok else "保存失败"
            self._config_hint.color = PALETTE.text_muted if ok else PALETTE.danger
            self.safe_update()

        self.run_intent(_save)

    def _on_restart_click(self, _e: ft.ControlEvent) -> None:
        bridge = self.ctx.bridge
        if bridge is None:
            return

        async def _restart() -> None:
            self._config_hint.value = "重启中…"
            self._config_hint.color = PALETTE.text_muted
            self.safe_update()
            ok = await bridge.restart_audio_source()
            # 重启会重读磁盘配置，丢弃未保存改动；重建编辑器以反映落盘后的值
            self._build_mic_config()
            self._config_hint.value = "已重启（已重读配置）" if ok else "重启失败"
            self._config_hint.color = PALETTE.text_muted if ok else PALETTE.danger
            self.safe_update()

        self.run_intent(_restart)

    @updates_ui
    def _on_audio_level(self, level: AudioLevelVM) -> None:
        self._audio_meter.update_level(level)

    @updates_ui
    def _on_audio_source(self, kind: AudioSourceKind) -> None:
        # 后端确认切换后：单选同步、解禁按钮、刷新文案
        self._draft = kind
        self._switching = False
        self._source_radio.value = kind.value
        self._active_hint.value = f"当前: {audio_source_label(kind)}"
        self._active_hint.color = PALETTE.text_muted
        self._update_switch_button()

    # —— 交互 ——
    @updates_ui
    def _on_radio_change(self, e: ft.ControlEvent) -> None:
        try:
            self._draft = AudioSourceKind(e.control.value)
        except ValueError:
            return
        self._update_switch_button()

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

        async def _switch() -> None:
            # 成功时由 _on_audio_source 回调复位 _switching；失败时后端不会推送
            # audio_source 变化，必须在此就地复位，否则按钮永久停在“切换中…”。
            try:
                await bridge.switch_audio_source(target)
            except Exception:
                logger.exception("切换音频源失败: {}", target)
                self._switching = False
                self._active_hint.value = "切换失败，请重试"
                self._active_hint.color = PALETTE.danger
                self._update_switch_button()
                self.safe_update()

        self.run_intent(_switch)

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

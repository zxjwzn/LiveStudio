"""音频设置页面。"""

from __future__ import annotations

import flet as ft

from livestudio.gui.components.common import card, page_body, page_title
from livestudio.gui.state import GUIState, PageId
from livestudio.gui.theme import Colors, Layout


class AudioPage(ft.Container):
    """音频页面示例。

    这里只放界面写法示例，暂时不接真实音频服务。
    后面需要接业务逻辑时，在按钮和下拉框的事件里补代码。
    """

    def __init__(self, state: GUIState) -> None:
        self.state = state
        self.page_state = state.page_state(PageId.AUDIO)
        self.source_group = ft.RadioGroup(
            value=self.page_state.values.get("source", "microphone"),
            content=ft.Row(
                [
                    ft.Radio(value="microphone", label="麦克风"),
                    ft.Radio(value="tts", label="TTS"),
                ],
                spacing=Layout.spacing_md,
            ),
            on_change=self._source_changed,
        )
        self.device_dropdown = ft.Dropdown(
            label="输入设备",
            value=self.page_state.values.get("device"),
            options=[ft.dropdown.Option("default", "默认设备")],
            border_color=Colors.border.hex,
            focused_border_color=Colors.accent.hex,
            on_change=self._device_changed,
        )
        super().__init__(
            expand=True,
            content=page_body(
                page_title("音频设置", "页面切换后控件状态会保留"),
                card("音频源", [self.source_group]),
                card("麦克风", [self.device_dropdown]),
            ),
        )

    def _source_changed(self, event: ft.ControlEvent) -> None:
        self.page_state.values["source"] = event.control.value
        self.state.status_message = f"音频源选择: {event.control.value}"

    def _device_changed(self, event: ft.ControlEvent) -> None:
        self.page_state.values["device"] = event.control.value
        self.state.status_message = f"设备选择: {event.control.value}"

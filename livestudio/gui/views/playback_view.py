"""音频播放页:配置音频总线的本机输出订阅方

订阅音频总线、按音频源标识过滤后用 sounddevice 输出到本机设备(可选虚拟声卡供 OBS
采集)。独立成页,排在音频页之后、日志页之前。保存时写盘并重建播放订阅方,使新输出设备/
过滤源/音量即时生效。
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    SingleDirectionScrollArea,
    SubtitleLabel,
)

from livestudio.gui.bridge import AudioController
from livestudio.gui.components.config_editor import ChoiceItem, ConfigEditor
from livestudio.gui.core import run_guarded
from livestudio.services.audio_stream.playback import PlaybackConfig


class PlaybackView(QWidget):
    """音频播放订阅方配置页"""

    def __init__(self, audio: AudioController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("playbackView")
        self._audio = audio
        self._output_choices: list[ChoiceItem] = []
        self._current: PlaybackConfig | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = SingleDirectionScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        outer.addWidget(scroll)

        content = QWidget(scroll)
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(SubtitleLabel("音频播放", content))

        self._editor: ConfigEditor[PlaybackConfig] = ConfigEditor(
            PlaybackConfig,
            choices_providers={"output_device": self._output_choice_items},
            scrollable=False,
            parent=content,
        )
        self._editor.saved.connect(self._on_saved)
        self._editor.validationFailed.connect(self._on_validation_failed)
        self._editor.reloadRequested.connect(self.refresh_devices)
        layout.addWidget(self._editor)
        layout.addStretch(1)

        # 用播放专用信号反馈,避免与音频页共享的 saveSucceeded/saveFailed 串扰
        audio.playbackSaveSucceeded.connect(self._on_save_succeeded)
        audio.playbackSaveFailed.connect(self._on_save_failed)

    def load_config(self) -> None:
        """加载当前播放配置并刷新输出设备下拉"""

        self._current = self._audio.playback_config()
        self._editor.load(self._current)
        run_guarded(self._reload_devices_then_fill())

    def refresh_devices(self) -> None:
        """重新枚举输出设备并刷新下拉候选,随后按当前配置回填选中项"""

        run_guarded(self._reload_devices_then_fill())

    def _output_choice_items(self) -> list[ChoiceItem]:
        return self._output_choices

    async def _reload_devices_then_fill(self) -> None:
        self._output_choices = await self._audio.list_output_device_choices()
        if self._current is not None:
            self._editor.load(self._current)

    def _on_saved(self, config: object) -> None:
        if isinstance(config, PlaybackConfig):
            self._current = config
            run_guarded(self._audio.save_playback_config(config))

    def _on_validation_failed(self, message: str) -> None:
        InfoBar.error("配置无效", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_save_succeeded(self) -> None:
        InfoBar.success("已保存", "配置已保存并应用", duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_save_failed(self, message: str) -> None:
        InfoBar.error("操作失败", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)

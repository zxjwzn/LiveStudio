"""音频页:放大电平表 + 音源切换 + 按音源加载对应配置编辑器 + 重载

顶部 SegmentedWidget 切换麦克风 / TTS 音源;切换即生效并保存为默认。下方 QStackedWidget
按当前音源显示对应配置编辑器(麦克风设备下拉 / TTS 占位参数)。「重载」就地重建当前
音源(换设备、恢复中断)。每个编辑器保存时写盘并按需重建流。
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import (
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PushButton,
    SegmentedWidget,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
)

from livestudio.gui.bridge import AudioController
from livestudio.gui.components.audio_meter import AudioMeter
from livestudio.gui.components.config_editor import ChoiceItem, ConfigEditor
from livestudio.gui.components.tts_speak_editor import TtsSpeakEditor
from livestudio.gui.constants import AUDIO_SOURCE_LABEL
from livestudio.gui.core import run_guarded
from livestudio.services.animations.controllers.config import TTSpeakControllerSettings
from livestudio.services.audio_stream.config import MicrophoneAudioStreamConfig
from livestudio.services.audio_stream.models import AudioSourceKind
from livestudio.services.audio_stream.sources.tts.config import TTSAudioStreamConfig


class AudioView(QWidget):
    """音频设备与电平页"""

    def __init__(self, audio: AudioController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("audioView")
        self._audio = audio
        self._device_choices: list[ChoiceItem] = []
        self._current_mic: MicrophoneAudioStreamConfig | None = None
        self._suppress_pivot = False

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
        layout.addWidget(SubtitleLabel("音频", content))

        self._meter = AudioMeter(large=True, parent=content)
        layout.addWidget(self._meter)
        audio.levelChanged.connect(self._meter.set_level)

        # --- 音源切换条 + 重载 ---
        source_row = QHBoxLayout()
        source_row.setSpacing(12)
        source_row.addWidget(StrongBodyLabel("音频源", content))
        self._pivot = SegmentedWidget(content)
        for kind in (AudioSourceKind.MICROPHONE, AudioSourceKind.TTS):
            self._pivot.addItem(routeKey=kind.value, text=AUDIO_SOURCE_LABEL[kind])
        self._pivot.currentItemChanged.connect(self._on_pivot_changed)
        source_row.addWidget(self._pivot)
        source_row.addStretch(1)
        self._reload_button = PushButton("重载", content)
        self._reload_button.setIcon(FIF.SYNC)
        self._reload_button.clicked.connect(self._on_reload)
        source_row.addWidget(self._reload_button)
        layout.addLayout(source_row)

        # --- TTS 测试(需先切到 TTS 音源才出声;置于配置编辑器上方) ---
        test_row = QHBoxLayout()
        test_row.setSpacing(12)
        test_row.addWidget(StrongBodyLabel("测试 TTS", content))
        self._tts_text = LineEdit(content)
        self._tts_text.setPlaceholderText("输入文本,需先切到 TTS 音源")
        test_row.addWidget(self._tts_text, 1)
        self._speak_btn = PushButton("播放", content)
        self._speak_btn.setIcon(FIF.PLAY)
        self._speak_btn.clicked.connect(self._on_speak)
        test_row.addWidget(self._speak_btn)
        self._stop_btn = PushButton("停止", content)
        self._stop_btn.setIcon(FIF.PAUSE)
        self._stop_btn.clicked.connect(self._on_stop_speaking)
        test_row.addWidget(self._stop_btn)
        layout.addLayout(test_row)

        # --- 按音源切换的配置编辑器 ---
        self._stack = QStackedWidget(content)
        layout.addWidget(self._stack)

        self._mic_editor: ConfigEditor[MicrophoneAudioStreamConfig] = ConfigEditor(
            MicrophoneAudioStreamConfig,
            choices_providers={"device_index": self._device_choice_items},
            scrollable=False,
            parent=self._stack,
        )
        self._mic_editor.saved.connect(self._on_mic_saved)
        self._mic_editor.validationFailed.connect(self._on_validation_failed)
        self._mic_editor.reloadRequested.connect(self.refresh_devices)
        self._stack.addWidget(self._mic_editor)

        # TTS 标签页:全局连接配置 + 当前模型发声配置(供应商切换)
        self._tts_page = QWidget(self._stack)
        tts_page_layout = QVBoxLayout(self._tts_page)
        tts_page_layout.setContentsMargins(0, 0, 0, 0)
        tts_page_layout.setSpacing(12)

        self._tts_editor: ConfigEditor[TTSAudioStreamConfig] = ConfigEditor(
            TTSAudioStreamConfig, scrollable=False, parent=self._tts_page
        )
        self._tts_editor.saved.connect(self._on_tts_saved)
        self._tts_editor.validationFailed.connect(self._on_validation_failed)
        tts_page_layout.addWidget(self._tts_editor)

        # 当前模型 TTS 发声:未连接/未加载模型时整段隐藏(不显示占位)
        self._speak_section = QWidget(self._tts_page)
        speak_section_layout = QVBoxLayout(self._speak_section)
        speak_section_layout.setContentsMargins(0, 0, 0, 0)
        speak_section_layout.setSpacing(8)
        speak_section_layout.addWidget(SubtitleLabel("当前模型 TTS 配置", self._speak_section))
        self._speak_editor = TtsSpeakEditor(self._speak_section)
        self._speak_editor.saved.connect(self._on_speak_saved)
        self._speak_editor.validationFailed.connect(self._on_validation_failed)
        speak_section_layout.addWidget(self._speak_editor)
        self._speak_section.setVisible(False)
        tts_page_layout.addWidget(self._speak_section)

        self._stack.addWidget(self._tts_page)
        layout.addStretch(1)

        audio.saveSucceeded.connect(self._on_save_succeeded)
        audio.saveFailed.connect(self._on_save_failed)
        audio.reloadSucceeded.connect(self._on_reload_succeeded)
        audio.reloadFailed.connect(self._on_save_failed)
        audio.modelChanged.connect(self._refresh_speak_config)
        audio.platformConnected.connect(self._on_platform_connected)
        audio.ttsSpeakSaveSucceeded.connect(self._on_speak_save_succeeded)
        audio.ttsSpeakSaveFailed.connect(self._on_speak_save_failed)

    def load_config(self) -> None:
        """按当前音源初始化切换条与对应编辑器"""

        kind = self._audio.active_source()
        # 程序化设置切换条不应触发 switch_source(避免初始化时多余的切换+落盘)
        self._suppress_pivot = True
        self._pivot.setCurrentItem(kind.value)
        self._suppress_pivot = False
        self._show_editor(kind)
        self._current_mic = self._audio.microphone_config()
        self._tts_editor.load(self._audio.tts_config())
        self._refresh_speak_config()
        run_guarded(self._reload_devices_then_fill())

    # --- 音源切换 ---

    def _on_pivot_changed(self, route_key: str) -> None:
        if self._suppress_pivot:
            return
        kind = AudioSourceKind(route_key)
        self._show_editor(kind)
        run_guarded(self._audio.switch_source(kind))

    def _show_editor(self, kind: AudioSourceKind) -> None:
        self._stack.setCurrentWidget(self._mic_editor if kind is AudioSourceKind.MICROPHONE else self._tts_page)

    def _on_reload(self) -> None:
        run_guarded(self._audio.reload_source())

    def _on_speak(self) -> None:
        text = self._tts_text.text().strip()
        if text:
            run_guarded(self._audio.speak(text))

    def _on_stop_speaking(self) -> None:
        run_guarded(self._audio.stop_speaking())

    # --- 设备候选(仅麦克风) ---

    def _device_choice_items(self) -> list[ChoiceItem]:
        return self._device_choices

    def refresh_devices(self) -> None:
        """重新枚举设备并刷新下拉候选,随后按当前配置回填选中项"""

        run_guarded(self._reload_devices_then_fill())

    async def _reload_devices_then_fill(self) -> None:
        self._device_choices = await self._audio.list_device_choices()
        if self._current_mic is not None:
            self._mic_editor.load(self._current_mic)
        self._audio.devicesReloaded.emit()

    # --- 保存回调 ---

    def _on_mic_saved(self, config: object) -> None:
        if isinstance(config, MicrophoneAudioStreamConfig):
            self._current_mic = config
            run_guarded(self._audio.save_microphone_config(config))

    def _on_tts_saved(self, config: object) -> None:
        if isinstance(config, TTSAudioStreamConfig):
            run_guarded(self._audio.save_tts_config(config))

    def _on_validation_failed(self, message: str) -> None:
        InfoBar.error("配置无效", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_save_succeeded(self) -> None:
        InfoBar.success("已保存", "配置已保存并应用", duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_save_failed(self, message: str) -> None:
        InfoBar.error("操作失败", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_reload_succeeded(self) -> None:
        InfoBar.success("已重载", "当前音源已重新加载", duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    # --- 当前模型 TTS 发声配置 ---

    def _refresh_speak_config(self) -> None:
        """从当前模型加载 TTS 发声配置;无模型(未连接/未加载)时隐藏整段。"""

        speak = self._audio.current_tts_speak()
        if speak is None:
            self._speak_section.setVisible(False)
            return
        self._speak_section.setVisible(True)
        self._speak_editor.load(speak)

    def _on_platform_connected(self, connected: bool) -> None:
        """平台连接态变化:未连接时隐藏发声段;已连接则按当前模型刷新。"""

        if not connected:
            self._speak_section.setVisible(False)
            return
        self._refresh_speak_config()

    def _on_speak_saved(self, speak: object) -> None:
        if isinstance(speak, TTSpeakControllerSettings):
            run_guarded(self._audio.save_tts_speak(speak))

    def _on_speak_save_succeeded(self) -> None:
        InfoBar.success("已保存", "TTS 发声配置已保存", duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_speak_save_failed(self, message: str) -> None:
        InfoBar.error("操作失败", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)
        self._refresh_speak_config()  # 回滚失败的标签切换/恢复到已存状态

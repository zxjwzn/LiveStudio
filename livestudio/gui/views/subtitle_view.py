"""字幕页:服务监听配置 + 字幕样式配置

上半为监听配置卡(host/port + 端点展示 + 应用并重启),结构与 MCP 页一致;
下半为字幕样式 ConfigEditor(font/color/delay 等),保存即落盘并应用。

全部使用 qfluentwidgets 原生组件。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    SettingCard,
    SingleDirectionScrollArea,
    SpinBox,
    StrongBodyLabel,
    SubtitleLabel,
)
from qfluentwidgets import FluentIcon as FIF

from livestudio.gui.bridge.subtitle_bridge import SubtitleBridge
from livestudio.gui.components.config_editor import ConfigEditor
from livestudio.gui.core import colors
from livestudio.services.subtitle import SubtitleConfig


class _ServiceCard(CardWidget):
    """监听配置卡:运行态 + 端点地址 + host/port 编辑 + 应用并重启"""

    def __init__(self, bridge: SubtitleBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = bridge

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # 头部:标题 + 运行态
        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(StrongBodyLabel("服务监听", self))
        self._state_label = CaptionLabel(self)
        header.addWidget(self._state_label)
        header.addStretch(1)
        root.addLayout(header)

        # 端点地址
        endpoint_row = QHBoxLayout()
        endpoint_row.setSpacing(8)
        endpoint_row.addWidget(CaptionLabel("OBS 浏览器源", self))
        self._endpoint_label = BodyLabel(self)
        self._endpoint_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        endpoint_row.addWidget(self._endpoint_label, 1)
        root.addLayout(endpoint_row)

        ws_row = QHBoxLayout()
        ws_row.setSpacing(8)
        ws_row.addWidget(CaptionLabel("WebSocket", self))
        self._ws_label = CaptionLabel(self)
        self._ws_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        ws_row.addWidget(self._ws_label, 1)
        root.addLayout(ws_row)

        # host
        config = bridge.current_config()
        host_card = SettingCard(
            FIF.GLOBE, "监听主机",
            "127.0.0.1 仅本机；0.0.0.0 对局域网开放（无鉴权，谨慎）",
            self,
        )
        self._host_edit = LineEdit(host_card)
        self._host_edit.setText(config.host)
        self._host_edit.setClearButtonEnabled(True)
        self._host_edit.setMinimumWidth(200)
        host_card.hBoxLayout.addWidget(self._host_edit, 0, Qt.AlignmentFlag.AlignRight)
        host_card.hBoxLayout.addSpacing(16)
        root.addWidget(host_card)

        # port
        port_card = SettingCard(FIF.CONNECT, "监听端口", "1–65535", self)
        self._port_spin = SpinBox(port_card)
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(config.port)
        self._port_spin.setMinimumWidth(140)
        port_card.hBoxLayout.addWidget(self._port_spin, 0, Qt.AlignmentFlag.AlignRight)
        port_card.hBoxLayout.addSpacing(16)
        root.addWidget(port_card)

        # 应用按钮
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self._apply_button = PrimaryPushButton("应用并重启", self)
        self._apply_button.setIcon(FIF.SYNC)
        self._apply_button.clicked.connect(self._on_apply)
        button_row.addWidget(self._apply_button)
        root.addLayout(button_row)

        bridge.configApplied.connect(self._on_applied)
        bridge.errorOccurred.connect(self._on_error)
        self._refresh()

    def _refresh(self) -> None:
        running = self._bridge.is_running()
        self._endpoint_label.setText(self._bridge.endpoint_url())
        self._ws_label.setText(self._bridge.ws_url())
        text = "运行中" if running else "未运行"
        color = QColor(colors.SUCCESS if running else colors.NEUTRAL)
        self._state_label.setText(text)
        self._state_label.setTextColor(color, color)

    def _on_apply(self) -> None:
        self._apply_button.setEnabled(False)
        self._apply_button.setText("应用中…")
        config = self._bridge.current_config()
        config.host = self._host_edit.text().strip()
        config.port = self._port_spin.value()
        self._bridge.apply_config(config)

    def _on_applied(self) -> None:
        self._restore_button()
        self._refresh()
        InfoBar.success(
            "已应用", "字幕服务已重启", duration=3000,
            position=InfoBarPosition.TOP_RIGHT, parent=self.window(),
        )

    def _on_error(self, message: str) -> None:
        self._restore_button()
        InfoBar.error("应用失败", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _restore_button(self) -> None:
        self._apply_button.setEnabled(True)
        self._apply_button.setText("应用并重启")


class SubtitleView(QWidget):
    """字幕页:服务监听 + 样式配置"""

    def __init__(self, bridge: SubtitleBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("subtitleView")
        self._bridge = bridge
        self._current: SubtitleConfig | None = None

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

        layout.addWidget(SubtitleLabel("字幕", content))
        self._service_card = _ServiceCard(bridge, content)
        layout.addWidget(self._service_card)

        layout.addWidget(StrongBodyLabel("字幕样式", content))
        self._editor: ConfigEditor[SubtitleConfig] = ConfigEditor(
            SubtitleConfig,
            scrollable=False,
            parent=content,
        )
        self._editor.saved.connect(self._on_saved)
        self._editor.validationFailed.connect(self._on_validation_failed)
        layout.addWidget(self._editor)
        layout.addStretch(1)

        bridge.configApplied.connect(self._on_config_applied)
        bridge.errorOccurred.connect(self._on_error)

    def load_config(self) -> None:
        self._current = self._bridge.current_config()
        self._editor.load(self._current)

    def _on_saved(self, config: object) -> None:
        if isinstance(config, SubtitleConfig):
            self._current = config
            self._bridge.apply_config(config)

    def _on_config_applied(self) -> None:
        if self._current is not None:
            self._editor.load(self._current)
        InfoBar.success("已保存", "字幕配置已保存并应用", duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_validation_failed(self, message: str) -> None:
        InfoBar.error("配置无效", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)

    def _on_error(self, message: str) -> None:
        InfoBar.error("操作失败", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self)

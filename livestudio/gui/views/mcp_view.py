"""MCP 页:工具一览 + 监听配置

上半为监听配置卡:host / port 编辑 + 端点地址展示 + 运行态徽标 + 应用按钮(改动落盘并
按需重启传输)。下半按分组展示已知工具:通用工具一组,每个平台特有工具一组,逐工具显示
名称与来自 docstring 的描述。

全部使用 qfluentwidgets 原生组件;遵循 ui-ux 规范:SettingCard 自带标签(form-labels)、
端口/主机失焦或点击「应用」时反馈 InfoBar(submit-feedback)、按钮异步期间禁用
(loading-buttons)、图标用 FluentIcon 矢量(no-emoji)。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentStyleSheet,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    SettingCard,
    SingleDirectionScrollArea,
    SpinBox,
    StrongBodyLabel,
    SubtitleLabel,
    TransparentToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from livestudio.gui.bridge import McpBridge, ToolGroup
from livestudio.gui.core import colors


class _ToolRow(CardWidget):
    """单个工具行:名称 + 描述(描述来自工具方法 docstring)。

    与平台页 _ModelCard 同款:用裸 QLabel + SettingCard 同款 objectName(titleLabel/contentLabel),
    并对整卡 apply SETTING_CARD 样式表,使名称/描述的字体与字色与 SettingCard 的标题/副标题
    (如「监听端口」「1-65535」)完全一致,且字色随主题(dark/light)自动切换,不再手设颜色。
    """

    def __init__(self, name: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        icon = TransparentToolButton(FIF.COMMAND_PROMPT, self)
        icon.setEnabled(False)  # 纯装饰,不可点
        layout.addWidget(icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title = QLabel(name, self)
        title.setObjectName("titleLabel")
        text_box.addWidget(title)
        desc = QLabel(description or "（无描述）", self)
        desc.setObjectName("contentLabel")
        desc.setWordWrap(True)
        text_box.addWidget(desc)
        layout.addLayout(text_box, 1)

        FluentStyleSheet.SETTING_CARD.apply(self)


class _ConfigCard(CardWidget):
    """监听配置卡:运行态 + 端点地址 + host/port 编辑 + 应用按钮"""

    def __init__(self, bridge: McpBridge, parent: QWidget | None = None) -> None:
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

        # 端点地址(只读展示 + 复制)
        endpoint_row = QHBoxLayout()
        endpoint_row.setSpacing(8)
        endpoint_row.addWidget(CaptionLabel("端点", self))
        self._endpoint_label = BodyLabel(self)
        self._endpoint_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        endpoint_row.addWidget(self._endpoint_label, 1)
        root.addLayout(endpoint_row)

        # host
        config = bridge.current_config()
        host_card = SettingCard(FIF.GLOBE, "监听主机", "127.0.0.1 仅本机；0.0.0.0 对局域网开放（无鉴权，谨慎）", self)
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
        """刷新运行态徽标与端点地址展示"""

        running = self._bridge.is_running()
        self._endpoint_label.setText(self._bridge.endpoint_url())
        text = "运行中" if running else "未运行"
        color = QColor(colors.SUCCESS if running else colors.NEUTRAL)
        self._state_label.setText(text)
        self._state_label.setTextColor(color, color)

    def _on_apply(self) -> None:
        # 异步期间禁用按钮(loading-buttons),完成/失败后由信号回调恢复。
        self._apply_button.setEnabled(False)
        self._apply_button.setText("应用中…")
        self._bridge.apply_config(self._host_edit.text().strip(), self._port_spin.value())

    def _on_applied(self, host: str, port: int) -> None:
        self._restore_button()
        self._refresh()
        InfoBar.success(
            "已应用",
            f"MCP 服务已在 {host}:{port} 上重启",
            duration=3000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )

    def _on_error(self, message: str) -> None:
        self._restore_button()
        InfoBar.error("应用失败", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _restore_button(self) -> None:
        self._apply_button.setEnabled(True)
        self._apply_button.setText("应用并重启")


class _ToolGroupCard(CardWidget):
    """一个工具分组卡:标题 + 副标题 + 该组工具行。

    标题/数量/副标题与 _ToolRow 同款:裸 QLabel + SettingCard objectName + apply SETTING_CARD,
    使字体字色与 SettingCard 标题/副标题一致并随主题切换,不手设颜色。
    """

    def __init__(self, group: ToolGroup, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel(group.title, self)
        title.setObjectName("titleLabel")
        header.addWidget(title)
        count = QLabel(f"{len(group.tools)} 个工具", self)
        count.setObjectName("contentLabel")
        header.addWidget(count)
        header.addStretch(1)
        root.addLayout(header)

        subtitle = QLabel(group.subtitle, self)
        subtitle.setObjectName("contentLabel")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        for tool in group.tools:
            root.addWidget(_ToolRow(tool.name, tool.description, self))

        FluentStyleSheet.SETTING_CARD.apply(self)


class McpView(QWidget):
    """MCP 页:监听配置 + 已知工具一览"""

    def __init__(self, bridge: McpBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("mcpView")
        self._bridge = bridge

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

        layout.addWidget(SubtitleLabel("MCP 服务", content))
        layout.addWidget(_ConfigCard(bridge, content))

        layout.addWidget(StrongBodyLabel("已知工具", content))
        for group in bridge.tool_groups():
            layout.addWidget(_ToolGroupCard(group, content))
        layout.addStretch(1)

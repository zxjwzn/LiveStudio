"""仪表盘页:实时音频电平 + 各平台运行态、控制器启停与表情触发

第一栏为固定的实时音频电平(复用 AudioMeter,不可折叠)。其后每个已注册平台一张
ExpandGroupSettingCard:头部显示连接态/模型,展开后依次为待机控制器开关、情绪表情
(AU 解算,点击播放一次性,通用能力)、原生表情(exp3,toggle 多选可激活/取消,仅带
native_expressions 能力的平台显示)。全部使用 qfluentwidgets 原生组件,不自封装。
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    DotInfoBadge,
    ExpandGroupSettingCard,
    FlowLayout,
    PillPushButton,
    PushButton,
    SimpleCardWidget,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    SwitchButton,
    TransparentToolButton,
)
from qfluentwidgets import FluentIcon as FIF

from livestudio.gui.bridge import AudioController, ConnectionState, PlatformBridge
from livestudio.gui.components.audio_meter import AudioMeter
from livestudio.gui.core import colors

_STATE_TEXT = {
    ConnectionState.DISCONNECTED: "未连接",
    ConnectionState.CONNECTING: "连接中…",
    ConnectionState.CONNECTED: "已连接",
    ConnectionState.ERROR: "连接错误",
}

_STATE_COLOR = {
    ConnectionState.DISCONNECTED: colors.NEUTRAL,
    ConnectionState.CONNECTING: colors.WARNING,
    ConnectionState.CONNECTED: colors.SUCCESS,
    ConnectionState.ERROR: colors.ERROR,
}

_CAP_NATIVE_EXPRESSIONS = "native_expressions"


class _FlowHost(QWidget):
    """把 FlowLayout 的按宽度高度暴露给父布局。"""

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        layout = self.layout()
        if layout is None:
            return super().heightForWidth(width)
        return layout.heightForWidth(width)

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        width = max(self.width(), hint.width())
        return QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self.updateGeometry()


class _PlatformCard(ExpandGroupSettingCard):
    """单个平台的折叠卡:头部连接态/模型 + 展开后控制器开关与快速表情。

    继承原生 ExpandGroupSettingCard,只往 viewLayout/addGroup 填原生子控件,不自绘卡片。
    """

    def __init__(self, bridge: PlatformBridge, parent: QWidget | None = None) -> None:
        super().__init__(bridge.icon, bridge.display_name, "未连接", parent)
        self._bridge = bridge
        self._switches: dict[str, SwitchButton] = {}
        self._suppress: set[str] = set()  # 程序化设置开关时抑制 checkedChanged

        # 头部:状态灯 + 模型名插到展开按钮(chevron)左侧,折叠态也可见。
        # 每次按 expandButton 的实时索引插入,使 chevron 始终保持在最右。
        self._badge = DotInfoBadge(self.card)
        self._model_label = CaptionLabel("", self.card)
        layout = self.card.hBoxLayout
        layout.insertWidget(layout.indexOf(self.card.expandButton), self._model_label)
        layout.insertSpacing(layout.indexOf(self.card.expandButton), 8)
        layout.insertWidget(layout.indexOf(self.card.expandButton), self._badge)
        layout.insertSpacing(layout.indexOf(self.card.expandButton), 12)

        self._build_controller_rows()
        self._build_emotion_row()
        self._build_native_expression_row()

        bridge.connectionStateChanged.connect(self._on_connection_changed)
        bridge.modelChanged.connect(self._on_model_changed)
        bridge.controllerStateChanged.connect(self._on_controller_state)
        bridge.controllersStateChanged.connect(lambda _running: self._refresh_controllers())
        bridge.nativeExpressionStateChanged.connect(self._on_native_expr_state)
        self._apply_state(bridge.state)

    # --- 构建(一次性,行集固定) ---

    def _build_controller_rows(self) -> None:
        for spec in self._bridge.controller_specs():
            switch = SwitchButton(self.card)
            switch.setOnText("运行中")
            switch.setOffText("已停止")
            switch.checkedChanged.connect(lambda checked, n=spec.name: self._on_switch_toggled(n, checked))
            self._switches[spec.name] = switch
            self.addGroup(spec.icon, spec.display_name, "", switch)

    def _build_emotion_row(self) -> None:
        """情绪表情区(AU 解算,点击播放一次性):仅支持的平台(emotion_specs 非空)显示"""

        self._emotion_buttons: list[PushButton] = []
        specs = self._bridge.emotion_specs()
        if not specs:
            self._emotion_row = None
            return
        row = QWidget(self.view)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(48, 12, 48, 12)
        layout.setSpacing(8)
        layout.addWidget(StrongBodyLabel("情绪表情", row))
        for spec in specs:
            button = PushButton(f"{spec.emoji} {spec.display_name}", row)
            button.clicked.connect(lambda _checked=False, k=spec.key: self._bridge.play_emotion(k))
            layout.addWidget(button)
            self._emotion_buttons.append(button)
        layout.addStretch(1)
        self._emotion_row = row
        self.addGroupWidget(row)

    def _build_native_expression_row(self) -> None:
        """原生表情区(exp3,toggle 多选):仅 VTS 等带 native_expressions 能力的平台显示"""

        self._native_chips: dict[str, PillPushButton] = {}
        if _CAP_NATIVE_EXPRESSIONS not in self._bridge.capabilities:
            self._native_row = None
            return
        row = QWidget(self.view)
        outer = QVBoxLayout(row)
        outer.setContentsMargins(48, 12, 48, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(StrongBodyLabel("原生表情", row))
        header.addStretch(1)
        self._native_clear = TransparentToolButton(FIF.DELETE, row)
        self._native_clear.setToolTip("取消所有原生表情")
        self._native_clear.clicked.connect(lambda: self._bridge.clear_native_expressions())
        header.addWidget(self._native_clear)
        outer.addLayout(header)

        self._native_chip_host = _FlowHost(row)
        self._native_flow = FlowLayout(self._native_chip_host, needAni=False)
        self._native_flow.setContentsMargins(0, 0, 0, 0)
        self._native_flow.setHorizontalSpacing(8)
        self._native_flow.setVerticalSpacing(8)
        outer.addWidget(self._native_chip_host)

        self._native_empty = CaptionLabel("无可用表情", row)
        outer.addWidget(self._native_empty)

        self._native_row = row
        self.addGroupWidget(row)

    # --- 开关交互 ---

    def _on_switch_toggled(self, name: str, checked: bool) -> None:
        if name in self._suppress:
            return
        if checked:
            self._bridge.start_controller(name)
        else:
            self._bridge.stop_controller(name)

    def _set_switch(self, name: str, checked: bool) -> None:
        """程序化设置开关态(抑制信号,避免回环触发启停)"""

        switch = self._switches.get(name)
        if switch is None or switch.isChecked() == checked:
            return
        self._suppress.add(name)
        switch.setChecked(checked)
        self._suppress.discard(name)

    def _on_controller_state(self, name: str, running: bool) -> None:
        self._set_switch(name, running)

    def _refresh_controllers(self) -> None:
        """按 bridge 实时控制器态回填所有开关;无控制器(未连接)时全部关闭"""

        running = {entry.name: entry.running for entry in self._bridge.controller_entries()}
        connected = self._bridge.state is ConnectionState.CONNECTED
        for name, switch in self._switches.items():
            switch.setEnabled(connected)
            self._set_switch(name, running.get(name, False))

    # --- 连接态 / 模型 ---

    def _on_connection_changed(self, state: ConnectionState) -> None:
        self._apply_state(state)

    def _apply_state(self, state: ConnectionState) -> None:
        self.card.setContent(_STATE_TEXT.get(state, ""))
        self._badge.setCustomBackgroundColor(QColor(_STATE_COLOR[state]), QColor(_STATE_COLOR[state]))
        if state is not ConnectionState.CONNECTED:
            self._model_label.setText("")
        self._refresh_controllers()
        self._refresh_emotions()
        self._refresh_native_expressions()

    def _on_model_changed(self, _model_id: str, model_name: str) -> None:
        self._model_label.setText(f"模型:{model_name}" if model_name else "")
        self._refresh_controllers()
        self._refresh_emotions()
        self._refresh_native_expressions()

    # --- 情绪表情(点击播放,未连接禁用) ---

    def _refresh_emotions(self) -> None:
        connected = self._bridge.state is ConnectionState.CONNECTED
        for button in self._emotion_buttons:
            button.setEnabled(connected)

    # --- 原生表情(toggle 多选) ---

    def _refresh_native_expressions(self) -> None:
        """按当前模型表情列表重建 chip,并回填激活态;未连接/无表情时显示占位"""

        if self._native_row is None:
            return
        for name, chip in list(self._native_chips.items()):
            self._native_flow.removeWidget(chip)
            chip.setParent(None)
            chip.deleteLater()
            del self._native_chips[name]

        connected = self._bridge.state is ConnectionState.CONNECTED
        names = self._bridge.native_expression_names() if connected else []
        active = self._bridge.active_native_expressions()
        self._native_empty.setVisible(not names)
        self._native_clear.setEnabled(connected and bool(names))
        for name in names:
            chip = PillPushButton(name, self._native_chip_host)
            chip.setChecked(name in active)
            chip.clicked.connect(lambda _checked=False, n=name: self._bridge.toggle_native_expression(n))
            self._native_flow.addWidget(chip)
            self._native_chips[name] = chip
        self._native_chip_host.updateGeometry()
        self._native_row.updateGeometry()

    def _on_native_expr_state(self, name: str, active: bool) -> None:
        chip = self._native_chips.get(name)
        if chip is None or chip.isChecked() == active:
            return
        # 程序化回填(如断开复位)不应回环触发 toggle;PillPushButton.setChecked 不发 clicked,
        # 故直接设置即可。
        chip.setChecked(active)


class DashboardView(QWidget):
    """仪表盘:实时音频电平(固定)+ 各平台运行态与控制器独立启停"""

    def __init__(
        self,
        audio: AudioController,
        platforms: Sequence[PlatformBridge],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("dashboardView")

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
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel("仪表盘", content))

        # 第一栏:实时音频电平(固定置顶,不可折叠)
        audio_card = SimpleCardWidget(content)
        audio_layout = QVBoxLayout(audio_card)
        audio_layout.setContentsMargins(16, 16, 16, 16)
        audio_layout.setSpacing(8)
        audio_layout.addWidget(StrongBodyLabel("实时音频电平", audio_card))
        meter = AudioMeter(parent=audio_card)
        audio_layout.addWidget(meter)
        audio.levelChanged.connect(meter.set_level)
        layout.addWidget(audio_card)

        # 第二栏起:每平台一张折叠卡
        for bridge in platforms:
            layout.addWidget(_PlatformCard(bridge, content))
        layout.addStretch(1)




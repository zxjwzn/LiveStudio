"""平台页:连接控制 + 模型配置(主从两级)

一级页平铺所有已注册平台,每平台一张卡:连接态/地址编辑/连接·断开·重连/LAN 搜索
(按 capability 显示)+ 该平台模型列表(每个模型一张卡,只显示模型名与 ID)。点击模型卡
进入二级页,用通用配置组件编辑该模型完整配置,保存回写 YAML;返回回到列表。

全部使用 qfluentwidgets 原生组件。平台循环渲染,新增平台只需提供 PlatformBridge,
本页无需改动。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    CardWidget,
    DotInfoBadge,
    FluentStyleSheet,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    SingleDirectionScrollArea,
    StrongBodyLabel,
    SubtitleLabel,
    TransparentToolButton,
    setCustomStyleSheet,
)
from qfluentwidgets import FluentIcon as FIF

from livestudio.gui.bridge import ConnectionState, ModelConfigEntry, PlatformBridge
from livestudio.gui.components.config_editor import ConfigEditor
from livestudio.gui.core import colors, run_guarded

_STATE_COLOR = {
    ConnectionState.DISCONNECTED: colors.NEUTRAL,
    ConnectionState.CONNECTING: colors.WARNING,
    ConnectionState.CONNECTED: colors.SUCCESS,
    ConnectionState.ERROR: colors.ERROR,
}

_LAN_DISCOVERY = "lan_discovery"


class _ModelCard(CardWidget):
    """单个模型配置项:只显示模型名 + ID,点击进入二级配置页(原生 CardWidget.clicked)"""

    def __init__(self, entry: ModelConfigEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.entry = entry
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        # 标题/ID 用裸 QLabel + SettingCard 同款 objectName,并对卡 apply SETTING_CARD,
        # 使字体/字色与配置页副标题等叶子 SettingCard 一致,字色交全局 QSS 随主题切换。
        name = entry.model_name or entry.display_name
        title = QLabel(name, self)
        title.setObjectName("titleLabel")
        text_box.addWidget(title)
        id_text = entry.model_id or entry.display_name
        id_label = QLabel(id_text, self)
        id_label.setObjectName("contentLabel")
        text_box.addWidget(id_label)
        layout.addLayout(text_box, 1)

        action = QLabel("配置", self)
        action.setObjectName("contentLabel")
        layout.addWidget(action)
        chevron = TransparentToolButton(FIF.CHEVRON_RIGHT, self)
        chevron.setEnabled(False)  # 纯指示,点击交给整卡 clicked
        layout.addWidget(chevron)

        FluentStyleSheet.SETTING_CARD.apply(self)


class _PlatformCard(CardWidget):
    """单平台卡:连接态 + 地址编辑 + 连接/断开/重连 + LAN搜索(capability) + 模型卡网格"""

    def __init__(
        self,
        bridge: PlatformBridge,
        on_open_model: "Callable[[PlatformBridge, ModelConfigEntry], None]",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._on_open_model = on_open_model

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # --- 头部:状态灯 + 平台名 ---
        header = QHBoxLayout()
        header.setSpacing(10)
        self._badge = DotInfoBadge(self)
        header.addWidget(self._badge)
        header.addWidget(StrongBodyLabel(bridge.display_name, self))
        header.addStretch(1)
        root.addLayout(header)

        # --- 地址行:LineEdit + 保存 + (LAN 搜索) ---
        if bridge.ws_url() or _LAN_DISCOVERY in bridge.capabilities:
            root.addLayout(self._build_address_row())

        # --- 按钮组:连接 / 断开 / 重连 ---
        root.addLayout(self._build_button_row())

        # --- 模型配置区 ---
        root.addWidget(StrongBodyLabel("模型配置", self))
        self._model_container = QWidget(self)
        self._model_grid = QGridLayout(self._model_container)
        self._model_grid.setContentsMargins(0, 0, 0, 0)
        self._model_grid.setSpacing(8)
        root.addWidget(self._model_container)
        self._empty_hint = CaptionLabel("未发现模型配置(连接并加载模型后自动生成)", self)
        self._empty_hint.setTextColor(QColor(colors.NEUTRAL), QColor(colors.NEUTRAL))
        root.addWidget(self._empty_hint)

        bridge.connectionStateChanged.connect(self._on_state_changed)
        bridge.errorOccurred.connect(self._on_error)
        bridge.modelChanged.connect(lambda *_: self.refresh_models())
        self._apply_state(bridge.state)
        self.refresh_models()

    # --- 地址行 ---

    def _build_address_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._address_edit = LineEdit(self)
        self._address_edit.setPlaceholderText("ws://127.0.0.1:8001")
        self._address_edit.setText(self._bridge.ws_url())
        self._address_edit.setClearButtonEnabled(True)
        # 失焦即保存(editingFinished 在回车/失焦时触发);仅地址变化时才落盘,避免无谓写盘。
        self._address_edit.editingFinished.connect(self._on_address_committed)
        row.addWidget(self._address_edit, 1)

        if _LAN_DISCOVERY in self._bridge.capabilities:
            self._lan_button = PushButton("局域网搜索", self)
            self._lan_button.setIcon(FIF.SEARCH)
            self._lan_button.clicked.connect(self._on_lan_search)
            row.addWidget(self._lan_button)
        return row

    # --- 按钮组 ---

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._connect_button = PrimaryPushButton("连接", self)
        self._connect_button.setIcon(FIF.CONNECT)
        self._connect_button.clicked.connect(lambda: self._bridge.connect_platform())
        self._disconnect_button = PushButton("断开", self)
        self._disconnect_button.clicked.connect(lambda: self._bridge.disconnect_platform())
        self._reconnect_button = PushButton("重连", self)
        self._reconnect_button.setIcon(FIF.SYNC)
        self._reconnect_button.clicked.connect(lambda: self._bridge.reconnect_platform())
        row.addWidget(self._connect_button)
        row.addWidget(self._disconnect_button)
        row.addWidget(self._reconnect_button)
        row.addStretch(1)
        return row

    # --- 模型列表 ---

    def refresh_models(self) -> None:
        """重新枚举模型配置并渲染模型卡(两列网格)"""

        while self._model_grid.count():
            item = self._model_grid.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        entries = self._bridge.discover_model_configs()
        self._empty_hint.setVisible(not entries)
        self._model_container.setVisible(bool(entries))
        for index, entry in enumerate(entries):
            card = _ModelCard(entry, self._model_container)
            card.clicked.connect(lambda _checked=False, e=entry: self._on_open_model(self._bridge, e))
            self._model_grid.addWidget(card, index // 2, index % 2)

    # --- 连接态 ---

    def _on_state_changed(self, state: ConnectionState) -> None:
        self._apply_state(state)

    def _apply_state(self, state: ConnectionState) -> None:
        color = QColor(_STATE_COLOR[state])
        self._badge.setCustomBackgroundColor(color, color)

        connecting = state is ConnectionState.CONNECTING
        connected = state is ConnectionState.CONNECTED
        # 连接按钮:未连接可点「连接」;连接中显示「连接中…」并禁用;已连接显示「已连接」并变绿。
        if connected:
            self._connect_button.setText("已连接")
        elif connecting:
            self._connect_button.setText("连接中…")
        else:
            self._connect_button.setText("连接")
        self._connect_button.setEnabled(not connecting and not connected)
        self._set_connect_button_success(connected)

        # 断开/重连:连接中也亮起,作为打断「连接中」状态的手段;未连接时禁用。
        self._disconnect_button.setEnabled(connecting or connected or state is ConnectionState.ERROR)
        self._reconnect_button.setEnabled(connecting or connected or state is ConnectionState.ERROR)

    def _set_connect_button_success(self, success: bool) -> None:
        """已连接时把「连接」主按钮染成成功绿;否则恢复 Fluent 原生外观。

        用 setCustomStyleSheet 追加自定义 QSS(不覆盖 qfluentwidgets 注入的原生样式);
        非成功态传空串即还原原生样式 —— 不能用 setStyleSheet,那会整体替换并清掉原生外观。
        """

        green = colors.SUCCESS
        qss = f"PrimaryPushButton {{ background-color: {green}; border: 1px solid {green}; }}" if success else ""
        setCustomStyleSheet(self._connect_button, qss, qss)

    def _on_error(self, message: str) -> None:
        InfoBar.error("操作失败", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    # --- 地址保存 / LAN 搜索 ---

    def _on_address_committed(self) -> None:
        """地址框失焦/回车:地址有变化才落盘(editingFinished 可能多次触发同一值)"""

        url = self._address_edit.text().strip()
        if url == self._bridge.ws_url():
            return
        run_guarded(self._save_address(url), on_error=self._guarded_error)

    async def _save_address(self, url: str) -> None:
        await self._bridge.apply_ws_url(url)
        InfoBar.success(
            "已保存", "连接地址已保存,重连后生效", duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
        )

    def _on_lan_search(self) -> None:
        self._lan_button.setEnabled(False)
        self._lan_button.setText("搜索中…")
        run_guarded(self._lan_search(), on_error=self._guarded_error)

    async def _lan_search(self) -> None:
        try:
            addresses = await self._bridge.discover_addresses()
        finally:
            self._lan_button.setEnabled(True)
            self._lan_button.setText("局域网搜索")
        if not addresses:
            InfoBar.warning(
                "未发现实例",
                "未发现局域网内的实例,请确认目标应用已开启 API",
                duration=4000,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )
            return
        if len(addresses) == 1:
            self._address_edit.setText(addresses[0])
            return
        menu = RoundMenu(parent=self._lan_button)
        for address in addresses:
            menu.addAction(Action(FIF.LINK, address, triggered=lambda _c=False, a=address: self._address_edit.setText(a)))
        menu.exec(self._lan_button.mapToGlobal(self._lan_button.rect().bottomLeft()))

    def _guarded_error(self, exc: BaseException) -> None:
        InfoBar.error("操作失败", str(exc), duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())


class _ModelConfigPage(QWidget):
    """二级页:单个模型的完整配置编辑(通用配置组件)+ 返回。

    每次打开一个模型都新建一个本页实例(配置组件按模型类型构建),关闭后销毁,避免
    在不同模型/平台间复用残留状态。
    """

    def __init__(
        self,
        bridge: PlatformBridge,
        entry: ModelConfigEntry,
        on_back: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._entry = entry
        self._on_back = on_back

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # 顶栏:返回 + 标题(模型名 · 平台)
        top = QHBoxLayout()
        top.setContentsMargins(24, 16, 24, 0)
        top.setSpacing(8)
        back = TransparentToolButton(FIF.RETURN, self)
        back.clicked.connect(on_back)
        top.addWidget(back)
        title = entry.model_name or entry.display_name
        top.addWidget(SubtitleLabel(f"{title} · {bridge.display_name}", self))
        top.addStretch(1)
        outer.addLayout(top)

        scroll = SingleDirectionScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        outer.addWidget(scroll)
        content = QWidget(scroll)
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 12, 24, 24)

        model_type = bridge.model_config_type()
        if model_type is None:
            layout.addWidget(BodyLabel("该平台无可编辑的模型配置", content))
            return
        self._editor: ConfigEditor[BaseModel] = ConfigEditor(model_type, parent=content)
        self._editor.saved.connect(self._on_saved)
        self._editor.validationFailed.connect(self._on_validation_failed)
        self._editor.reloadRequested.connect(self._load)
        layout.addWidget(self._editor)

        self._load()

    def _load(self) -> None:
        run_guarded(self._load_async(), on_error=self._guarded_error)

    async def _load_async(self) -> None:
        config = await self._bridge.load_model_config(self._entry.path)
        self._editor.load(config)

    def _on_saved(self, config: BaseModel) -> None:
        run_guarded(self._save_async(config), on_error=self._guarded_error)

    async def _save_async(self, config: BaseModel) -> None:
        await self._bridge.save_model_config(self._entry.path, config)
        InfoBar.success("已保存", "模型配置已保存", duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _on_validation_failed(self, message: str) -> None:
        InfoBar.error("配置无效", message, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _guarded_error(self, exc: BaseException) -> None:
        InfoBar.error("操作失败", str(exc), duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())


class PlatformView(QWidget):
    """平台页:主从两级(平台列表 ↔ 模型配置)"""

    def __init__(self, platforms: Sequence[PlatformBridge], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("platformView")
        self._stack = QStackedWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._stack)

        # 一级页:平台列表
        self._list_page = QWidget(self._stack)
        list_outer = QVBoxLayout(self._list_page)
        list_outer.setContentsMargins(0, 0, 0, 0)
        scroll = SingleDirectionScrollArea(self._list_page)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        list_outer.addWidget(scroll)
        content = QWidget(scroll)
        content.setStyleSheet("background: transparent;")
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.addWidget(SubtitleLabel("平台", content))
        self._cards: list[_PlatformCard] = []
        for bridge in platforms:
            card = _PlatformCard(bridge, self._open_model, content)
            self._cards.append(card)
            layout.addWidget(card)
        layout.addStretch(1)
        self._stack.addWidget(self._list_page)

        self._config_page: _ModelConfigPage | None = None

    def _open_model(self, bridge: PlatformBridge, entry: ModelConfigEntry) -> None:
        if self._config_page is not None:
            self._stack.removeWidget(self._config_page)
            self._config_page.deleteLater()
        self._config_page = _ModelConfigPage(bridge, entry, self._close_model, self._stack)
        self._stack.addWidget(self._config_page)
        self._stack.setCurrentWidget(self._config_page)

    def _close_model(self) -> None:
        self._stack.setCurrentWidget(self._list_page)
        for card in self._cards:
            card.refresh_models()

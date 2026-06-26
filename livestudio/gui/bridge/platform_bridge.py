"""平台桥接抽象

定义连接态枚举与平台桥接基类。GUI 视图只依赖本抽象暴露的信号与方法,不直接 import
后端平台类型。连接态由桥接层自行维护(后端无 is_connected,且 start 会无限重试)。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from qfluentwidgets import FluentIcon


class ConnectionState(Enum):
    """平台连接状态(桥接层维护)"""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class ModelConfigEntry:
    """平台模型配置文件的发现结果(展示名 + 文件路径)"""

    display_name: str
    path: Path


class PlatformBridge(QObject):
    """平台桥接基类:连接控制 + 状态/模型/控制器信号 + capability 声明。

    平台页(ConnectionCard / ModelSection)只依赖本基类的方法与信号,故同一套 UI 可承载
    任意平台。连接/地址/模型枚举给出默认实现(空/未实现),具体平台按需覆盖。
    """

    connectionStateChanged = Signal(ConnectionState)
    modelChanged = Signal(str, str)  # model_id, model_name
    controllersStateChanged = Signal(bool)  # 是否运行中
    errorOccurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = ConnectionState.DISCONNECTED

    @property
    def platform_name(self) -> str:
        """平台唯一标识(用作 pivot routeKey 等),子类必须实现"""

        raise NotImplementedError

    @property
    def display_name(self) -> str:
        """平台展示名(连接卡标题、平台切换条),子类必须实现"""

        raise NotImplementedError

    @property
    def icon(self) -> FluentIcon:
        """平台图标(连接卡横幅),子类必须实现"""

        raise NotImplementedError

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def capabilities(self) -> frozenset[str]:
        """平台能力标签(如 "lan_discovery"),驱动 UI 条件显示"""

        return frozenset()

    # --- 连接控制(平台页连接卡消费;子类覆盖)---

    def connect_platform(self) -> None:
        raise NotImplementedError

    def disconnect_platform(self) -> None:
        raise NotImplementedError

    def reconnect_platform(self) -> None:
        raise NotImplementedError

    def ws_url(self) -> str:
        """当前连接地址(无地址概念的平台返回空串)"""

        return ""

    async def apply_ws_url(self, ws_url: str) -> None:
        """写入连接地址(无地址概念的平台为空操作)"""

    async def discover_addresses(self) -> list[str]:
        """LAN 搜索候选地址;无该能力的平台返回空列表(UI 以 capability 门控,通常不会调到)"""

        return []

    # --- 模型配置(平台页模型区消费;子类覆盖)---

    def discover_model_configs(self) -> list[ModelConfigEntry]:
        """枚举该平台的模型配置;无模型概念的平台返回空列表"""

        return []

    def current_model_stem(self) -> str | None:
        """当前已加载模型对应的配置文件名(用于高亮);无则 None"""

        return None

    def _set_state(self, state: ConnectionState) -> None:
        if state is not self._state:
            self._state = state
            self.connectionStateChanged.emit(state)

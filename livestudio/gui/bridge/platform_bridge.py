"""平台桥接抽象

定义连接态枚举与平台桥接基类。GUI 视图只依赖本抽象暴露的信号与方法,不直接 import
后端平台类型。连接态由桥接层自行维护(后端无 is_connected,且 start 会无限重试)。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path

from pydantic import BaseModel
from PySide6.QtCore import QObject, Signal
from qfluentwidgets import FluentIcon

from livestudio.app.base import PlatformStateEvent, PlatformStateKind


class ConnectionState(Enum):
    """平台连接状态(桥接层维护)"""

    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class ModelConfigEntry:
    """平台模型配置文件的发现结果(展示名 + 模型名/ID + 文件路径)。

    model_name/model_id 供列表分开展示;display_name 为文件 stem(无法读出 identity 时回退)。
    """

    display_name: str
    path: Path
    model_name: str = ""
    model_id: str = ""


@dataclass(frozen=True, slots=True)
class ControllerEntry:
    """一个待机动画控制器的展示信息(供仪表盘开关行)"""

    name: str  # 控制器内部名(如 "blink"),启停时回传
    display_name: str  # 中文展示名
    running: bool  # 当前是否运行中


@dataclass(frozen=True, slots=True)
class ControllerSpec:
    """待机动画控制器的静态展示规格(与连接态无关,供仪表盘一次性建开关行)"""

    name: str  # 控制器内部名(如 "blink"),启停时回传
    display_name: str  # 中文展示名
    icon: FluentIcon  # 行首图标(平台自带,使控制器行不依赖视图层硬编码图标表)


@dataclass(frozen=True, slots=True)
class EmotionSpec:
    """情绪表情(AU 解算)的静态展示规格,供仪表盘一次性建情绪按钮"""

    key: str  # 情绪标识(EmotionKind 值,如 "joy"),触发时回传
    display_name: str  # 中文展示名(如 "喜悦")
    emoji: str  # 按钮前缀 emoji(用户要求,情绪用 emoji 直观区分)


class PlatformBridge(QObject):
    """平台桥接基类:连接控制 + 状态/模型/控制器信号 + capability 声明。

    平台页(ConnectionCard / ModelSection)只依赖本基类的方法与信号,故同一套 UI 可承载
    任意平台。连接/地址/模型枚举给出默认实现(空/未实现),具体平台按需覆盖。
    """

    connectionStateChanged = Signal(ConnectionState)
    modelChanged = Signal(str, str)  # model_id, model_name
    controllersStateChanged = Signal(bool)  # 是否运行中(整体)
    controllerStateChanged = Signal(str, bool)  # 单个控制器: name, running
    nativeExpressionStateChanged = Signal(str, bool)  # 原生表情: name, active
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
    # 缺省为安全空操作(非 raise):未实现连接的平台(如示例占位平台)按钮可见但点击无副作用,
    # 视图层无需对"是否支持连接"做特判。

    def connect_platform(self) -> None:
        """发起连接(子类覆盖;缺省空操作)"""

    def disconnect_platform(self) -> None:
        """断开连接(子类覆盖;缺省空操作)"""

    def reconnect_platform(self) -> None:
        """重连(子类覆盖;缺省空操作)"""

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

    def model_config_type(self) -> type[BaseModel] | None:
        """该平台模型配置的 Pydantic 类型(供通用配置组件渲染);无模型概念返回 None"""

        return None

    async def load_model_config(self, path: Path) -> BaseModel:
        """加载单个模型配置文件(子类覆盖);无模型概念时抛错(UI 不会调到)"""

        raise NotImplementedError

    async def save_model_config(self, path: Path, config: BaseModel) -> None:
        """保存单个模型配置文件(子类覆盖)"""

        raise NotImplementedError

    # --- 动画控制器启停(仪表盘消费;子类覆盖)---

    def controller_specs(self) -> list[ControllerSpec]:
        """可独立启停的待机控制器静态清单(name/展示名/图标),与连接态无关。

        仪表盘据此一次性建出固定的开关行(未连接时禁用),避免按连接/模型变化反复重建。
        """

        return []

    def controller_entries(self) -> list[ControllerEntry]:
        """当前可独立启停的待机动画控制器列表(含实时运行态);未连接/无控制器时返回空"""

        return []

    def start_controller(self, name: str) -> None:
        """启动单个动画控制器(仅运行态,不改配置)"""

    def stop_controller(self, name: str) -> None:
        """停止单个动画控制器(仅运行态,不改配置)"""

    # --- 情绪表情(AU 解算,通用能力;支持的平台覆盖)---

    def emotion_specs(self) -> list[EmotionSpec]:
        """可触发的情绪表情清单(喜怒哀乐…);不支持 AU 解算的平台返回空,UI 不画情绪区"""

        return []

    def play_emotion(self, key: str) -> None:
        """触发一次情绪表情解算(一次性:过渡→保持→自动回 neutral);子类覆盖"""

    # --- 原生表情(平台特有,如 VTS exp3;可激活/取消的 toggle)---

    def native_expression_names(self) -> list[str]:
        """当前模型可 toggle 的原生表情名;无模型/不支持时返回空"""

        return []

    def active_native_expressions(self) -> set[str]:
        """当前已激活的原生表情名集合(供 UI 回填 toggle 态)"""

        return set()

    def toggle_native_expression(self, name: str) -> None:
        """切换一个原生表情的激活/取消(子类覆盖);结果经 nativeExpressionStateChanged 通知"""

    def clear_native_expressions(self) -> None:
        """取消所有已激活的原生表情(子类覆盖)"""

    # --- app 运行态事件 -> Qt 信号(单一事实源在后端,GUI 与 MCP 共享) ---

    def _on_state_event(self, event: PlatformStateEvent) -> None:
        """app 运行态变更 -> 同步 GUI 连接徽标与控制器开关。

        GUI 按钮与 MCP 工具都经 app 公开方法变更态,app 广播事件,本方法据此 emit Qt
        信号,使两条路径都能驱动视图刷新(MCP 路径不再因绕过 bridge 而让 GUI 停在旧态)。
        """

        if self._should_suppress_state_event(event):
            return
        kind = event.kind
        if kind is PlatformStateKind.CONNECTED:
            self._set_state(ConnectionState.CONNECTED)
        elif kind is PlatformStateKind.DISCONNECTED:
            self._set_state(ConnectionState.DISCONNECTED)
            self.controllersStateChanged.emit(False)
        elif kind is PlatformStateKind.CONTROLLERS_STARTED:
            self.controllersStateChanged.emit(True)
        elif kind is PlatformStateKind.CONTROLLERS_STOPPED:
            self.controllersStateChanged.emit(False)
        elif (
            kind is PlatformStateKind.CONTROLLER_CHANGED
            and event.name is not None
            and event.active is not None
        ):
            self.controllerStateChanged.emit(event.name, event.active)
        elif (
            kind is PlatformStateKind.NATIVE_EXPRESSION_CHANGED
            and event.name is not None
            and event.active is not None
        ):
            self._on_native_expression_changed(event.name, event.active)

    def _on_native_expression_changed(self, name: str, active: bool) -> None:
        """app 原生表情变更 -> emit 信号让仪表盘 chip 同步。

        基类默认仅发信号;维护激活镜像的平台在子类覆盖:先更新镜像再 super 发信号,
        使刷新(读镜像)不会把 MCP 等非 GUI 来源的激活态回弹。
        """

        self.nativeExpressionStateChanged.emit(name, active)

    def _should_suppress_state_event(self, _event: PlatformStateEvent) -> bool:
        """是否抑制本次 app 运行态事件(基类默认不抑制;子类按需覆盖)。

        连接/重连在途时,app 内部 disconnect->connect 步骤会短暂触发 DISCONNECTED,那是
        编排细节而非真实断开--由在途任务决定终态,子类可覆盖本方法抑制之以避免 UI 闪烁。
        """

        return False

    def _set_state(self, state: ConnectionState) -> None:
        if state is not self._state:
            self._state = state
            self.connectionStateChanged.emit(state)

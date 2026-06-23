"""GUI 专用 view-model

GUI 不复用后端 Pydantic 模型，统一在此定义只读 dataclass。
后端类型 -> view-model 的转换发生在对应 Adapter / Controller 中，
视图层永远只见到这些结构，从而与后端解耦。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal


class ConnectionState(str, Enum):
    """平台连接状态。"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ControllerState(str, Enum):
    """动画控制器运行状态。"""

    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


class AudioSourceKind(str, Enum):
    """音频源类型（与后端同名枚举对应，但属于 GUI 自有定义）。"""

    MICROPHONE = "microphone"
    TTS = "tts"


# 音频源类型 -> 中文展示标签的权威映射（视图层统一复用，避免多处副本各自维护）
AUDIO_SOURCE_LABELS: dict[AudioSourceKind, str] = {
    AudioSourceKind.MICROPHONE: "麦克风",
    AudioSourceKind.TTS: "TTS",
}


def audio_source_label(source: AudioSourceKind) -> str:
    """返回音频源的中文标签；未知类型回退到其原始值。"""

    return AUDIO_SOURCE_LABELS.get(source, source.value)


# 连接状态 -> 中文展示标签的权威映射（仪表盘、顶栏、平台页统一复用）
CONNECTION_LABELS: dict[ConnectionState, str] = {
    ConnectionState.DISCONNECTED: "未连接",
    ConnectionState.CONNECTING: "连接中",
    ConnectionState.CONNECTED: "已连接",
    ConnectionState.RECONNECTING: "重连中",
    ConnectionState.ERROR: "连接错误",
}


def connection_label(state: ConnectionState) -> str:
    """返回连接状态的中文标签；未知状态回退到其原始值。"""

    return CONNECTION_LABELS.get(state, state.value)


# —— 平台相关 ——————————————————————————————————————————————


@dataclass(frozen=True)
class PlatformDescriptor:
    """平台静态元信息，注册到 PlatformRegistry。

    adapter_factory / panel_factory 使用 Any 标注以避免 core 层反向依赖
    bridge / views 的具体类型，真正的签名约定见各自抽象基类。
    """

    id: str  # "vtube_studio"
    display_name: str  # "VTube Studio"
    icon: str  # ft.Icons 名
    adapter_factory: Any  # (state, async_bridge) -> PlatformAdapter
    panel_factory: Any  # (ctx) -> PlatformPanel


@dataclass(frozen=True)
class PlatformStatusVM:
    """平台运行态快照，驱动仪表盘与平台页状态区。"""

    platform_id: str
    display_name: str
    connection: ConnectionState = ConnectionState.DISCONNECTED
    endpoint: str = ""  # 当前连接地址
    model_name: str = ""  # 已加载模型名，空 = 未加载
    model_id: str = ""
    detail: str = ""  # 错误 / 重连等附加描述


@dataclass(frozen=True)
class DiscoveredEndpointVM:
    """LAN 发现结果项。"""

    name: str
    host: str
    port: int

    @property
    def address(self) -> str:
        return f"ws://{self.host}:{self.port}"


# —— 动画控制器与表情 ————————————————————————————————————————


@dataclass(frozen=True)
class ControllerVM:
    """单个动画控制器的展示态。"""

    key: str  # "blink" / "breathing" ...
    display_name: str  # "眨眼"
    type: Literal["idle", "oneshot"] = "idle"
    state: ControllerState = ControllerState.STOPPED
    enabled: bool = True  # 模型配置中是否启用


@dataclass(frozen=True)
class ExpressionVM:
    """可快速触发的表情项。"""

    key: str  # 情绪 / 表情标识，如 "happy"
    display_name: str  # "开心"
    emoji: str = ""  # 可选图标
    is_native: bool = False  # True = 直接触发 exp3.json


# —— 音频与日志 ——————————————————————————————————————————————


@dataclass(frozen=True)
class AudioLevelVM:
    """实时电平快照（高频更新，已在 Controller 节流）。"""

    rms: float = 0.0  # 0..1
    peak: float = 0.0  # 0..1
    source: AudioSourceKind = AudioSourceKind.MICROPHONE
    active: bool = False


@dataclass(frozen=True)
class LogEntryVM:
    """单条日志记录。"""

    ts: str  # 已格式化时间串 "HH:MM:SS.mmm"
    level: str  # "INFO" / "WARNING" ...
    message: str
    color: str  # 由 level 预解析的 PALETTE 颜色 token


# —— 模型配置编辑（数据驱动骨架，字段级 UI 后续设计）————————————————


@dataclass(frozen=True)
class ChoiceVM:
    """下拉选项：展示标签与实际值解耦（如设备名 -> 设备索引）。"""

    value: Any
    label: str


ValueType = Literal["bool", "int", "float", "str", "enum", "group", "list", "dict"]


@dataclass(frozen=True)
class ConfigFieldVM:
    """单个可编辑配置项的描述符（数据驱动渲染）。

    核心设计：数据类型（value_type）与渲染控件（widget）解耦。
    - value_type 说明「数据是什么」：bool/int/float/str/enum/group/list/dict。
    - widget 说明「怎么渲染」：查 WidgetRegistry 的 key；"auto" 按 value_type
      取默认控件。同一个 int 可在 slider / spinbox / number 间切换，只改 widget。
    - 自定义控件（旋钮、颜色选择器等）= 注册一个新 renderer，无需改编辑器。

    复合结构递归：
    - group：固定子字段，用 fields 描述。
    - list：变长，用 item_template 描述每项的形状，支持增删。
    - dict：键值对，用 item_template 描述值的形状，支持加键。
    """

    path: str  # 配置中的点路径 "microphone.samplerate"；list 项用 "expressions[0].name"
    label: str
    value_type: ValueType
    widget: str = "auto"  # WidgetRegistry 的 key；"auto" 按 value_type 取默认控件
    value: Any = None
    default: Any = None
    # enum 选项：静态 choices，或经 ChoicesRegistry 异步拉取的动态源
    choices: tuple[ChoiceVM, ...] = ()
    choices_source: str = ""
    # 数值约束（int/float，滑块/旋钮也用）
    min: float | None = None
    max: float | None = None
    step: float | None = None
    # 复合结构
    fields: tuple["ConfigFieldVM", ...] = ()  # value_type=group 的固定子字段
    item_template: "ConfigFieldVM | None" = None  # value_type=list/dict 的每项形状
    help: str = ""


@dataclass(frozen=True)
class ConfigSectionVM:
    """配置分区，如「动画控制器」「语义参数」「表情状态」。"""

    id: str  # "controllers" / "semantic_profile" ...
    title: str
    fields: tuple[ConfigFieldVM, ...] = ()
    subsections: tuple["ConfigSectionVM", ...] = ()


@dataclass(frozen=True)
class ModelConfigVM:
    """整个模型配置的可编辑视图。"""

    model_id: str
    model_name: str
    sections: tuple[ConfigSectionVM, ...] = ()
    dirty: bool = False  # 是否有未保存修改

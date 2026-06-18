"""GUI 专用 view-model

GUI 不复用后端 Pydantic 模型，统一在此定义只读 dataclass。
后端类型 -> view-model 的转换发生在对应 Adapter / Controller 中，
视图层永远只见到这些结构，从而与后端解耦。
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
class AudioDeviceVM:
    """音频输入设备。"""

    index: int
    name: str
    is_default: bool = False


@dataclass(frozen=True)
class LogEntryVM:
    """单条日志记录。"""

    ts: str  # 已格式化时间串 "HH:MM:SS.mmm"
    level: str  # "INFO" / "WARNING" ...
    message: str
    color: str  # 由 level 预解析的 PALETTE 颜色 token


# —— 模型配置编辑（数据驱动骨架，字段级 UI 后续设计）————————————————


@dataclass(frozen=True)
class ConfigFieldVM:
    """单个可编辑配置项的描述符（数据驱动渲染）。"""

    path: str  # 模型配置中的点路径 "controllers.blink.interval"
    label: str
    kind: Literal["bool", "int", "float", "text", "enum", "range", "group"]
    value: Any = None
    default: Any = None
    choices: tuple[str, ...] = ()  # kind=enum
    min: float | None = None  # kind=int/float/range
    max: float | None = None
    step: float | None = None
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
    raw: dict = field(default_factory=dict)  # 原始 dict，保存时回写兜底

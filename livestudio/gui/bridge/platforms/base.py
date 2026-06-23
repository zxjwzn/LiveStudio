"""平台适配器抽象 + 平台上下文。

PlatformAdapter 是桥接层面向「平台」的核心契约：把某个后端平台服务的事件
转换为 view-model 写入 AppState，并把 UI 意图转为后端 async 调用。新增平台
只需实现本接口并注册到 PlatformRegistry。

PlatformContext 是构造适配器时注入的依赖包：除 AppState / AsyncBridge 外，
还携带共享后端基础设施（动画管理器、音频路由器），供适配器装配自身的后端应用。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...core.app_state import AppState
from ...core.async_bridge import AsyncBridge
from ...core.view_models import DiscoveredEndpointVM, ModelConfigSummaryVM, PlatformStatusVM

if TYPE_CHECKING:
    from livestudio.services.animations import AnimationManager
    from livestudio.services.audio_stream import AudioStreamRouter


@dataclass
class PlatformContext:
    """构造平台适配器时注入的依赖包。"""

    state: AppState
    async_bridge: AsyncBridge
    animation_manager: "AnimationManager"
    audio_router: "AudioStreamRouter"


class PlatformAdapter(ABC):
    """平台扩展的核心契约。"""

    platform_id: str = ""
    display_name: str = ""

    def __init__(self, ctx: PlatformContext) -> None:
        self.ctx = ctx
        self.state = ctx.state
        self.async_bridge = ctx.async_bridge

    # —— 生命周期 ——
    @abstractmethod
    async def start(self) -> None:
        """初始化后端应用并写入初始状态（不应阻塞等待连接）。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止后端应用并释放资源。"""

    # —— 连接 ——
    @abstractmethod
    async def connect(self, endpoint: str | None = None) -> None:
        """连接到平台（endpoint 为空则用配置默认值）。"""

    @abstractmethod
    async def disconnect(self) -> None:
        """断开平台连接。"""

    @abstractmethod
    async def discover(self) -> list[DiscoveredEndpointVM]:
        """LAN 发现可用平台端点。"""

    # —— 状态快照 ——
    @abstractmethod
    def status_vm(self) -> PlatformStatusVM:
        """返回当前平台状态快照。"""

    # —— 动画控制器代理 ——
    @abstractmethod
    async def set_controller_enabled(self, key: str, enabled: bool) -> None:
        """启动 / 停止指定 idle 控制器任务。"""

    # —— 表情 ——
    @abstractmethod
    async def trigger_expression(self, key: str) -> None:
        """触发一次表情解算（key 为情绪标识）。"""

    # —— 模型配置文件管理 (P4) ——
    @abstractmethod
    async def list_model_configs(self) -> list[ModelConfigSummaryVM]:
        """枚举该平台所有已存在的模型配置文件摘要。"""

    @abstractmethod
    async def load_model_config_raw(self, file_stem: str) -> "Any":
        """加载指定模型配置的 Pydantic 实例（供 GUI 反射）。返回 PlatformModelConfig 子类实例。"""

    @abstractmethod
    async def save_model_config_raw(self, file_stem: str, data: dict) -> None:
        """把编辑后的字典原子写回 YAML。"""

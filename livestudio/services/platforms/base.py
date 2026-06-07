"""平台服务抽象"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Literal

from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.services.semantic_actions.adapter import (
    SemanticActionAdapter,
    SemanticActionState,
)
from livestudio.services.semantic_actions.models import SemanticTweenRequest
from livestudio.tween import ControlledParameterState, ParameterTweenEngine


class PlatformService(AsyncServiceLifecycleMixin, ABC):
    """所有平台服务必须实现的统一生命周期接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """平台唯一名称"""

    @property
    @abstractmethod
    def tween(self) -> ParameterTweenEngine:
        """返回平台参数缓动引擎"""

    @property
    def semantic_adapter(self) -> SemanticActionAdapter | None:
        """返回平台语义动作适配器；未支持的平台可保持为空"""

        return None

    async def tween_semantic(self, request: SemanticTweenRequest) -> None:
        """将平台无关语义动作缓动解析并发送到底层参数缓动引擎"""

        adapter = self.semantic_adapter
        if adapter is None:
            raise NotImplementedError(f"平台 {self.name} 未实现语义动作适配器")
        await adapter.tween(self.tween, request)

    async def get_semantic_value(self, action: str) -> SemanticActionState | None:
        """查询平台真实参数值并归一化为语义动作值"""

        _ = action
        return None

    async def send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"] = "set",
    ) -> None:
        """发送一批底层平台参数状态"""

        await self._send_parameter_states(states, mode)

    @abstractmethod
    async def _send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"] = "set",
    ) -> None:
        """平台实现的底层参数发送逻辑"""

    @abstractmethod
    async def initialize(self) -> None:
        """初始化平台服务"""

    @abstractmethod
    async def start(self) -> None:
        """启动平台服务"""

    @abstractmethod
    async def stop(self) -> None:
        """停止平台服务并释放资源"""


"""平台服务抽象"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal

from livestudio.services.expression.models import NativeExpressionTrigger
from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.services.semantic_actions import (
    SemanticActionAdapter,
    SemanticTweenRequest,
)
from livestudio.services.tween import ControlledParameterState, ParameterTweenEngine

if TYPE_CHECKING:
    # 仅用于类型注解;运行时导入会触发 platforms → base → model → animations → platforms 循环。
    from livestudio.services.platforms.model import PlatformModelIdentity


class PlatformService(AsyncServiceLifecycleMixin, ABC):
    """所有平台服务必须实现的统一生命周期接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """平台唯一名称"""

    @property
    def current_model(self) -> PlatformModelIdentity:
        """返回当前已加载模型身份。

        基类默认视作「无模型概念/未加载」而抛 RuntimeError;有模型概念的平台覆盖此属性,
        在未加载时同样按约定抛 RuntimeError。app 层的 current_model 据此收敛为可空返回。
        """

        raise RuntimeError(f"平台 {self.name} 当前没有已加载的模型")

    @property
    @abstractmethod
    def tween(self) -> ParameterTweenEngine:
        """返回平台参数缓动引擎"""

    @property
    def semantic_adapter(self) -> SemanticActionAdapter | None:
        """返回平台语义动作适配器；未支持的平台可保持为空"""

        return None

    async def tween_semantic(self, requests: Iterable[SemanticTweenRequest]) -> None:
        """将平台无关语义动作缓动解析并发送到底层参数缓动引擎"""

        adapter = self.semantic_adapter
        if adapter is None:
            raise NotImplementedError(f"平台 {self.name} 未实现语义动作适配器")
        await adapter.apply(tuple(requests))

    async def get_semantic_value(self, action: str) -> float | None:
        """查询当前受控参数并返回语义动作瞬时值"""

        adapter = self.semantic_adapter
        if adapter is None:
            return None
        return adapter.query(action)

    async def apply_native_expressions(
        self,
        triggers: Iterable[NativeExpressionTrigger],
        *,
        fade_time: float | None = None,
        scope: str = "default",
    ) -> None:
        """应用平台原生表情触发（如 VTS .exp3.json）

        默认无操作；支持原生表情的平台覆盖此方法。表情解算层只产出
        平台无关的 NativeExpressionTrigger，由各平台自行翻译为原生调用。

        fade_time：原生表情淡入/淡出时长，None 时由平台决定默认值。
        表情控制器会传入与语义过渡一致的 transition_duration。

        scope：标识触发来源（如情绪解算 vs 手动 toggle）。支持原生表情的平台
        按来源分别管理期望集，使不同来源点亮的表情互不误关。
        """

        _ = triggers, fade_time, scope

    @abstractmethod
    async def send_parameter_states(
        self,
        states: Iterable[ControlledParameterState],
        mode: Literal["set", "add"] = "set",
    ) -> None:
        """发送一批底层平台参数状态"""

    # 生命周期 start/restart/stop 由 AsyncServiceLifecycleMixin 统一提供，
    # 平台子类只需实现 _do_start / _do_stop（按需 _do_restart）副作用。

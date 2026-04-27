"""平台服务抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from livestudio.tween import ParameterTweenEngine


class PlatformService(ABC):
    """所有平台服务必须实现的统一生命周期接口。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """平台唯一名称。"""

    @property
    @abstractmethod
    def tween(self) -> ParameterTweenEngine:
        """返回平台参数缓动引擎。"""

    @abstractmethod
    async def initialize(self) -> None:
        """初始化平台服务。"""

    @abstractmethod
    async def start(self) -> None:
        """启动平台服务。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止平台服务并释放资源。"""

"""动画控制器注册表。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .base import AnimationController
from .config import ControllerSettings

ControllerFactory = Callable[
    [str, ControllerSettings],
    AnimationController[ControllerSettings],
]
ControllerKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class ControllerRegistration:
    """已注册控制器元数据。"""

    platform_name: str
    controller_name: str
    factory: ControllerFactory


class AnimationControllerRegistry:
    """按平台命名空间管理动画控制器工厂。"""

    def __init__(self) -> None:
        self._registrations: dict[ControllerKey, ControllerRegistration] = {}

    def register(
        self,
        platform_name: str,
        controller_name: str,
        factory: ControllerFactory,
        *,
        replace: bool = False,
    ) -> None:
        """注册某个平台下的控制器工厂。"""

        key = self._build_key(platform_name, controller_name)
        if not replace and key in self._registrations:
            raise ValueError(
                f"动画控制器已注册: {platform_name}.{controller_name}",
            )
        self._registrations[key] = ControllerRegistration(
            platform_name=platform_name,
            controller_name=controller_name,
            factory=factory,
        )

    def unregister(self, platform_name: str, controller_name: str) -> None:
        """移除某个平台下的控制器注册。"""

        key = self._build_key(platform_name, controller_name)
        self._registrations.pop(key, None)

    def get(
        self,
        platform_name: str,
        controller_name: str,
    ) -> ControllerRegistration:
        """获取某个平台下的控制器注册。"""

        key = self._build_key(platform_name, controller_name)
        registration = self._registrations.get(key)
        if registration is None:
            raise KeyError(f"未知动画控制器: {platform_name}.{controller_name}")
        return registration

    def create(
        self,
        platform_name: str,
        controller_name: str,
        config: ControllerSettings,
    ) -> AnimationController[ControllerSettings]:
        """根据注册工厂创建控制器实例。"""

        registration = self.get(platform_name, controller_name)
        return registration.factory(controller_name, config)

    def list_for_platform(self, platform_name: str) -> list[ControllerRegistration]:
        """列出某个平台下的全部控制器注册。"""

        return [
            registration
            for registration in self._registrations.values()
            if registration.platform_name == platform_name
        ]

    def list_all(self) -> list[ControllerRegistration]:
        """列出全部控制器注册。"""

        return list(self._registrations.values())

    def has(self, platform_name: str, controller_name: str) -> bool:
        """检查控制器是否已注册。"""

        return self._build_key(platform_name, controller_name) in self._registrations

    def clear(self) -> None:
        """清空注册表。"""

        self._registrations.clear()

    def _build_key(self, platform_name: str, controller_name: str) -> ControllerKey:
        return (platform_name, controller_name)

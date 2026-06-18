"""注册表：平台与视图的装配中心。

新增平台只需在启动时 ``register(PlatformDescriptor(...))`` 一行，
导航、仪表盘、平台页都会自动纳入，无需改动壳层代码。
"""

from __future__ import annotations

from .view_models import PlatformDescriptor


class PlatformRegistry:
    """持有所有平台静态元信息（PlatformDescriptor）。"""

    def __init__(self) -> None:
        self._items: dict[str, PlatformDescriptor] = {}

    def register(self, descriptor: PlatformDescriptor) -> None:
        """登记一个平台；同 id 重复登记将覆盖。"""

        self._items[descriptor.id] = descriptor

    def all(self) -> list[PlatformDescriptor]:
        """按注册顺序返回全部平台。"""

        return list(self._items.values())

    def get(self, platform_id: str) -> PlatformDescriptor | None:
        """按 id 取平台元信息，不存在返回 None。"""

        return self._items.get(platform_id)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, platform_id: object) -> bool:
        return platform_id in self._items

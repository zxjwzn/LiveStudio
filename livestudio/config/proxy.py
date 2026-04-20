"""通过属性访问暴露配置值的运行时配置对象。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

ConfigT = TypeVar("ConfigT", bound=BaseModel)
UpdateHook = Callable[[str, Any], None]
SnapshotGetter = Callable[[], ConfigT]


class ConfigProxy(Generic[ConfigT]):
    """稳定的运行时配置引用，委托到最新的已校验快照。"""

    def __init__(
        self,
        snapshot_getter: SnapshotGetter[ConfigT],
        update_hook: UpdateHook | None = None,
    ) -> None:
        object.__setattr__(self, "_snapshot_getter", snapshot_getter)
        object.__setattr__(self, "_update_hook", update_hook)

    def __getattr__(self, item: str) -> Any:
        snapshot = self._snapshot_getter()
        return getattr(snapshot, item)

    def __setattr__(self, key: str, value: Any) -> None:
        if key.startswith("_"):
            object.__setattr__(self, key, value)
            return
        update_hook = self._update_hook
        if update_hook is None:
            raise AttributeError(f"配置代理为只读对象，无法设置 {key}")
        update_hook(key, value)

    def snapshot(self) -> ConfigT:
        """返回最新的不可变配置快照。"""

        return self._snapshot_getter()

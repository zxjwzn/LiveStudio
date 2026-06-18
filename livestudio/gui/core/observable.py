"""最小响应式原语：Observable / ObservableList

Flet 没有内建的响应式机制，这里实现一个轻量的可观察值容器。
后端事件经桥接层写入 Observable，视图订阅后在值变更时刷新自身。
"""

from __future__ import annotations

from typing import Callable, Generic, Iterable, TypeVar

T = TypeVar("T")

# 订阅回调与退订句柄的类型别名
Listener = Callable[[T], None]
Unsubscribe = Callable[[], None]


class Observable(Generic[T]):
    """持有单个值，值变更时通知所有订阅者。"""

    def __init__(self, value: T) -> None:
        self._value = value
        self._listeners: list[Listener[T]] = []

    @property
    def value(self) -> T:
        """当前值（只读访问）。"""

        return self._value

    def set(self, value: T) -> None:
        """写入新值；与旧值相等时不触发通知（去抖）。"""

        if value == self._value:
            return
        self._value = value
        self._emit()

    def update(self, mutator: Callable[[T], T]) -> None:
        """基于旧值计算新值并写入。"""

        self.set(mutator(self._value))

    def notify(self) -> None:
        """强制通知一次（用于就地修改了可变值的场景）。"""

        self._emit()

    def subscribe(self, listener: Listener[T], *, immediate: bool = True) -> Unsubscribe:
        """注册订阅者，返回退订句柄。

        immediate 为 True 时立即用当前值回调一次，便于视图首帧渲染。
        退订句柄交由 BaseView 统一登记与调用。
        """

        self._listeners.append(listener)
        if immediate:
            listener(self._value)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def _emit(self) -> None:
        # 遍历副本，允许回调内部退订而不影响本轮通知
        for listener in list(self._listeners):
            listener(self._value)


class ObservableList(Observable[list[T]]):
    """列表型 Observable，提供常用就地操作（日志缓冲、发现列表等）。

    所有写操作都会生成新列表后调用 set，从而触发去抖与通知。
    """

    def __init__(self, value: list[T] | None = None) -> None:
        super().__init__(list(value) if value is not None else [])

    def append(self, item: T, *, cap: int | None = None) -> None:
        """追加一项；指定 cap 时保留末尾 cap 条（环形缓冲）。"""

        data = list(self._value)
        data.append(item)
        if cap is not None and len(data) > cap:
            data = data[-cap:]
        self.set(data)

    def extend(self, items: Iterable[T], *, cap: int | None = None) -> None:
        """批量追加；指定 cap 时保留末尾 cap 条。"""

        data = list(self._value)
        data.extend(items)
        if cap is not None and len(data) > cap:
            data = data[-cap:]
        self.set(data)

    def replace(self, items: Iterable[T]) -> None:
        """整体替换为新的元素序列。"""

        self.set(list(items))

    def clear(self) -> None:
        """清空列表。"""

        self.set([])

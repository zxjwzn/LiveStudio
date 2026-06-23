"""挂载感知与订阅生命周期 mixin。

视图 / 外壳级控件共用的横切基础设施，集中三件物：

- ``MountAware``：统一"仅挂载时刷新"守卫（``safe_update``）。BaseView /
  AppShell / ConfigEditor 此前各写一份，收敛到单一实现。
- ``updates_ui``：方法装饰器，方法执行完毕后自动 ``safe_update``，消除每个
  事件回调结尾手写的刷新调用。
- ``SubscriptionHost``：Observable 订阅的生命周期宿主，统一登记退订句柄、
  卸载时批量释放，避免 BaseView 与 AppShell 各维护一套订阅管理。

团队约定（推广原则）：
1. 视图 / 外壳级控件 → 继承 ``MountAware`` + ``SubscriptionHost``。
2. 事件回调若"执行后需整体刷新且无中途异步" → 加 ``@updates_ui``；
   否则手写 ``safe_update`` 并注释原因（如异步流程中途穿插刷新）。
3. 禁止再各自实现 ``safe_update`` / ``_safe_update``。
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar

from .observable import Observable

_F = TypeVar("_F", bound=Callable[..., None])


class MountAware:
    """为 flet 控件提供挂载守卫的 ``update``。

    依赖宿主类具有 flet Control 的 ``page`` 属性与 ``update()`` 方法
    （ft.Container / ft.Row / ft.Column 等均满足）。``self`` 不强标 ft.Control：
    mixin 在 MRO 中先于 flet 控件，运行时由宿主提供这两个成员。
    """

    def safe_update(self) -> None:
        """仅在已挂载（page 就绪）时刷新，避免未挂载控件 update 报错。"""

        if self.page is not None:  # type: ignore[attr-defined]
            self.update()  # type: ignore[attr-defined]


def updates_ui(method: _F) -> _F:
    """方法装饰器：方法执行完毕后自动调用 ``self.safe_update()``。

    替代每个事件回调结尾手写的 ``self.safe_update()``——把"改完状态要刷新"
    这一横切关注点从散落调用收敛为一个声明。装饰的方法本身只关心"改了哪些
    控件属性"，刷新时机交给装饰器，杜绝漏写导致的 UI 不刷新；多分支函数也
    只需装饰一次，而非每条提前 return 前各补一行。

    要求宿主具有 ``safe_update()``（即继承 ``MountAware``）。方法抛异常时不
    刷新（异常向上传播，由既有日志 / 兜底处理）。
    """

    @wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> None:
        method(self, *args, **kwargs)
        self.safe_update()

    return wrapper  # type: ignore[return-value]


class SubscriptionHost:
    """Observable 订阅的生命周期宿主：统一登记退订句柄，卸载时批量释放。

    BaseView 与 AppShell 共用：避免 AppShell 手工维护 _unsub_* 字段 + 手写
    遍历退订（与 BaseView.watch 并存的第二套订阅管理）。

    宿主须在 ``__init__`` 内调用 ``_init_subscriptions()`` 初始化句柄列表，
    在卸载钩子（``will_unmount``）内调用 ``release_subscriptions()``。
    """

    def _init_subscriptions(self) -> None:
        """初始化退订句柄列表（在订阅建立前调用）。"""

        self._unsubs: list[Callable[[], None]] = []

    def watch(self, observable: Observable, handler: Callable, *, immediate: bool = True) -> None:
        """订阅 ``observable`` 并登记退订句柄，由 ``release_subscriptions`` 统一释放。"""

        self._unsubs.append(observable.subscribe(handler, immediate=immediate))

    def release_subscriptions(self) -> None:
        """退订全部已登记的订阅。"""

        for unsubscribe in self._unsubs:
            unsubscribe()
        self._unsubs.clear()

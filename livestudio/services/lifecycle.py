"""异步服务生命周期辅助工具"""

from types import TracebackType
from typing import Self


class AsyncServiceLifecycleMixin:
    """为 initialize/start/stop 风格服务提供统一上下文管理。

    子类应重写 ``_do_initialize`` / ``_do_start`` / ``_do_stop`` 实现真正的副作用，
    幂等守卫、状态标志维护与启动失败回滚都由本 Mixin 统一处理：

    - ``initialize()`` 已初始化时直接返回，成功后置 ``_initialized``。
    - ``start()`` 已启动时直接返回，未初始化时自动初始化；``_do_start`` 抛错时
      调用 ``stop()`` 回滚并重新抛出。
    - ``stop()`` 未初始化时直接返回，结束后清空 ``_started`` 与 ``_initialized``。
    """

    _initialized: bool = False
    _started: bool = False

    @property
    def is_initialized(self) -> bool:
        """服务是否已初始化。"""

        return self._initialized

    @property
    def is_started(self) -> bool:
        """服务是否已启动。"""

        return self._started

    def _mark_initialized(self, value: bool = True) -> None:
        self._initialized = value

    def _mark_started(self, value: bool = True) -> None:
        self._started = value

    def _mark_stopped(self, *, reset_initialized: bool = False) -> None:
        self._started = False
        if reset_initialized:
            self._initialized = False

    async def _do_initialize(self) -> None:
        """子类重写以执行实际初始化副作用。"""

    async def _do_start(self) -> None:
        """子类重写以执行实际启动副作用。"""

    async def _do_stop(self) -> None:
        """子类重写以执行实际停止副作用。"""

    async def initialize(self) -> None:
        """初始化服务资源（幂等）。"""

        if self._initialized:
            return
        await self._do_initialize()
        self._mark_initialized()

    async def start(self) -> None:
        """启动服务（幂等，失败时自动回滚）。"""

        if self._started:
            return
        if not self._initialized:
            await self.initialize()
        try:
            await self._do_start()
        except Exception:
            await self.stop()
            raise
        self._mark_started()

    async def stop(self) -> None:
        """停止服务并释放资源（幂等）。"""

        if not self._initialized:
            return
        await self._do_stop()
        self._mark_stopped(reset_initialized=True)

    async def restart(self) -> None:
        """重启服务。"""

        await self.stop()
        await self.start()

    async def __aenter__(self) -> Self:
        await self.initialize()
        try:
            await self.start()
        except Exception:
            await self.stop()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        _ = exc_type, exc, traceback
        await self.stop()
        return False

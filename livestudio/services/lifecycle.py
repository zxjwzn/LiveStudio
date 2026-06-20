"""异步服务生命周期辅助工具"""

from types import TracebackType
from typing import Self


class AsyncServiceLifecycleMixin:
    """为 initialize/start/restart/stop 风格服务提供统一生命周期。

    四件套语义（全系统统一）：

    - ``initialize()`` —— 一次性准备资源（解析设备、建客户端等），幂等。即使某服务
      不需要初始化，也保留该阶段：默认 ``_do_initialize`` 为空占位，无需改动。
    - ``start()`` —— 进入运行态，幂等；未初始化时自动 ``initialize``；``_do_start``
      抛错时回滚（调 ``stop``）并重新抛出。
    - ``restart()`` —— **软重启**：服务保持初始化，只回收并重建运行态。默认
      ``_do_restart`` = ``_do_stop`` + ``_do_start``；需要保留对外契约（如已建立的
      订阅者）的服务重写 ``_do_restart`` 定制。
    - ``stop()`` —— **唯一的真正退出**：释放全部资源、断开对外契约，并复位
      ``_started`` 与 ``_initialized``。未初始化时为空操作（幂等）。

    子类只重写 ``_do_initialize`` / ``_do_start`` / ``_do_stop``（按需重写
    ``_do_restart``）实现真实副作用；幂等守卫、标志维护、失败回滚均由本 Mixin 统一处理。
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

    async def _do_restart(self) -> None:
        """子类重写以执行软重启副作用。

        默认实现 = ``_do_stop`` + ``_do_start``：回收并重建运行态。需要在重启时
        保留对外契约（如已建立的订阅者）的服务重写本方法，仅重建必要的内部运行态，
        不触碰对外资源。仅在服务处于运行态（``restart`` 内）被调用。
        """

        await self._do_stop()
        await self._do_start()

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
        """停止服务并释放资源（幂等）。

        即使 ``_do_stop`` 抛错，也在 ``finally`` 里复位标志：``stop`` 是终止入口，
        清理出错也不应把服务卡在「运行中」，资源按尽力而为释放。
        """

        if not self._initialized:
            return
        try:
            await self._do_stop()
        finally:
            self._mark_stopped(reset_initialized=True)

    async def restart(self) -> None:
        """软重启服务（保持已初始化状态）。

        语义区别于 ``stop`` + ``start``：``restart`` 不销毁服务（不复位
        ``_initialized``），只回收并重建运行态，因此对外契约（已建立的订阅者等）
        默认得以保留——具体由 ``_do_restart`` 决定。语义上只有 ``stop`` 才是真正的
        终止与资源释放。

        - 未初始化：等价一次 ``start``（会先 ``initialize``）。
        - 已初始化未启动：仅 ``start``。
        - 运行中：调用 ``_do_restart`` 重建运行态；失败时回滚到 ``stop``。
        """

        if not self._initialized:
            await self.start()
            return
        if not self._started:
            await self.start()
            return
        try:
            await self._do_restart()
        except Exception:
            await self.stop()
            raise

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

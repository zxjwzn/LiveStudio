"""异步服务生命周期辅助工具"""

from types import TracebackType
from typing import Self

from livestudio.utils.log import logger


class AsyncServiceLifecycleMixin:
    """为 start/restart/stop 风格服务提供统一生命周期。

    三件套语义（全系统统一）：

    - ``start()`` —— 进入运行态：解析资源、建客户端、订阅等一次性准备与启动副作用
      都在这里完成，幂等；``_do_start`` 抛错时回滚（调 ``stop``）并重新抛出。
    - ``restart()`` —— **以新状态重新部署**：未启动时等价 ``start``；运行中则调
      ``_do_restart`` 重建运行态（重读配置、重解析资源）。默认 ``_do_restart`` =
      ``_do_stop`` + ``_do_start``；需要保留对外契约（如已建立的订阅者）的服务重写
      ``_do_restart`` 定制。
    - ``stop()`` —— **唯一的真正退出**：释放全部资源、断开对外契约，并复位
      ``_started``。未启动时为空操作（幂等）。

    子类只重写 ``_do_start`` / ``_do_stop``（按需重写 ``_do_restart``）实现真实副作用；
    幂等守卫、标志维护、失败回滚均由本 Mixin 统一处理。
    """

    _started: bool = False

    @property
    def is_started(self) -> bool:
        """服务是否已启动。"""

        return self._started

    def _mark_started(self, value: bool = True) -> None:
        self._started = value

    def _mark_stopped(self) -> None:
        self._started = False

    async def _do_start(self) -> None:
        """子类重写以执行实际启动副作用。"""

    async def _do_stop(self) -> None:
        """子类重写以执行实际停止副作用。"""

    async def _do_restart(self) -> None:
        """子类重写以执行重启副作用。

        默认实现 = ``_do_stop`` + ``_do_start``：回收并以新状态重建运行态。需要在
        重启时保留对外契约（如已建立的订阅者）的服务重写本方法，仅重建必要的内部
        运行态，不触碰对外资源。仅在服务处于运行态（``restart`` 内）被调用。
        """

        await self._do_stop()
        await self._do_start()

    async def start(self) -> None:
        """启动服务（幂等，失败时自动回滚）。"""

        if self._started:
            return
        try:
            await self._do_start()
        except Exception:
            # 此时 _started 仍为 False，stop() 会空转，故直接调 _do_stop 清理已产生的
            # 副作用；回滚清理本身若抛错不应掩盖原始启动异常：记录后让原异常继续传播。
            try:
                await self._do_stop()
            except Exception:
                logger.exception("启动失败后的回滚清理出错，已记录但仍抛出原始启动异常")
            raise
        self._mark_started()

    async def stop(self) -> None:
        """停止服务并释放资源（幂等）。

        即使 ``_do_stop`` 抛错，也在 ``finally`` 里复位标志：``stop`` 是终止入口，
        清理出错也不应把服务卡在「运行中」，资源按尽力而为释放。
        """

        if not self._started:
            return
        try:
            await self._do_stop()
        finally:
            self._mark_stopped()

    async def restart(self) -> None:
        """重启服务：以新状态重新部署。

        语义区别于 ``stop`` + ``start``：运行中的 ``restart`` 不一定销毁对外契约
        （已建立的订阅者等），而是调用 ``_do_restart`` 以新状态（重读配置、重解析
        资源）重建运行态——具体由 ``_do_restart`` 决定。语义上只有 ``stop`` 才是真正的
        终止与资源释放。

        - 未启动：等价一次 ``start``。
        - 运行中：调用 ``_do_restart`` 重建运行态；失败时回滚到 ``stop``。
        """

        if not self._started:
            await self.start()
            return
        try:
            await self._do_restart()
        except Exception:
            # 回滚清理本身若抛错，不应掩盖原始重启异常：记录后让原异常继续传播
            try:
                await self.stop()
            except Exception:
                logger.exception("重启失败后的回滚清理出错，已记录但仍抛出原始重启异常")
            raise

    async def __aenter__(self) -> Self:
        try:
            await self.start()
        except Exception:
            # 回滚清理本身若抛错，不应掩盖原始启动异常：记录后让原异常继续传播
            try:
                await self.stop()
            except Exception:
                logger.exception("进入异步上下文失败后的回滚清理出错，已记录但仍抛出原始异常")
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

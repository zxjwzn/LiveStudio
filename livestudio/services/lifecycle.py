"""异步服务生命周期辅助工具"""

from types import TracebackType
from typing import Self


class AsyncServiceLifecycleMixin:
    """为 initialize/start/stop 风格服务提供统一上下文管理。"""

    @property
    def is_initialized(self) -> bool:
        """服务是否已初始化。"""

        return bool(getattr(self, "_initialized", False))

    @property
    def is_started(self) -> bool:
        """服务是否已启动。"""

        return bool(getattr(self, "_started", False))

    def _mark_initialized(self, value: bool = True) -> None:
        self._initialized = value

    def _mark_started(self, value: bool = True) -> None:
        self._started = value

    def _mark_stopped(self, *, reset_initialized: bool = False) -> None:
        self._started = False
        if reset_initialized:
            self._initialized = False

    async def initialize(self) -> None:
        """初始化服务资源。"""

    async def start(self) -> None:
        """启动服务。"""

    async def stop(self) -> None:
        """停止服务并释放资源。"""

    async def restart(self) -> None:
        """重启服务。"""

        await self.stop()
        await self.initialize()
        try:
            await self.start()
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

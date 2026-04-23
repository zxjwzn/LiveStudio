"""核心配置管理器。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import ConfigLoadError, ConfigValidationError
from .store import ConfigStore

ConfigT = TypeVar("ConfigT", bound=BaseModel)


class ConfigManager(Generic[ConfigT]):
    """管理经校验的配置快照，并提供显式保存语义。"""

    def __init__(
        self,
        model_type: type[ConfigT],
        path: str | Path,
        *,
        store: ConfigStore | None = None,
        auto_create: bool = True,
    ) -> None:
        self._model_type = model_type
        self._path = Path(path)
        self._store = store or ConfigStore()
        self._auto_create = auto_create
        self._lock = asyncio.Lock()
        self._current = model_type()

    @property
    def config(self) -> ConfigT:
        """返回最新的已校验配置快照。"""

        return self._current

    @property
    def path(self) -> Path:
        """返回配置文件路径。"""

        return self._path

    async def load(self) -> ConfigT:
        """从磁盘加载配置，或在内存中以默认值初始化。"""

        async with self._lock:
            if self._path.exists():
                config = self._load_from_disk()
                self._current = config
                return config

            if not self._auto_create:
                raise ConfigLoadError(f"配置文件不存在: {self._path}")

            return self._current

    async def save(self) -> None:
        """将当前快照持久化到磁盘。"""

        async with self._lock:
            self._persist_snapshot(self._current)

    def _load_from_disk(self) -> ConfigT:
        data = self._store.load_dict(self._path)
        try:
            return self._model_type.model_validate(data)
        except ValidationError as exc:
            raise ConfigValidationError(f"配置校验失败: {self._path}") from exc

    def _persist_snapshot(self, config: ConfigT) -> None:
        self._store.save_dict(
            self._path, config.model_dump(mode="json", exclude_none=True)
        )

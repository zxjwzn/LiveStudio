"""核心配置管理器。"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .errors import ConfigLoadError, ConfigValidationError
from .models import ConfigChangeEvent, ConfigSource, FileVersion
from .store import ConfigStore

ConfigT = TypeVar("ConfigT", bound=BaseModel)
ConfigSubscriber = Callable[[ConfigChangeEvent[ConfigT]], Awaitable[None] | None]


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
        self._subscribers: list[ConfigSubscriber[ConfigT]] = []
        self._current = model_type()
        self._last_written_version: FileVersion | None = None

    @property
    def config(self) -> ConfigT:
        """返回最新的已校验配置快照。"""

        return self._current

    @property
    def path(self) -> Path:
        """返回配置文件路径。"""

        return self._path

    def get_snapshot(self) -> ConfigT:
        """返回最新的不可变配置快照。"""

        return self._current

    async def load(self) -> ConfigT:
        """从磁盘加载配置，或在内存中以默认值初始化。"""

        async with self._lock:
            if self._path.exists():
                config = self._load_from_disk()
                self._current = config
                self._last_written_version = self._store.get_version(self._path)
                return config

            if not self._auto_create:
                raise ConfigLoadError(f"配置文件不存在: {self._path}")

            return self._current

    async def reload(self) -> ConfigT:
        """显式地从磁盘重新加载配置。"""

        async with self._lock:
            version = self._store.get_version(self._path)
            if version is None:
                raise ConfigLoadError(f"配置文件不存在: {self._path}")
            if version == self._last_written_version:
                return self._current

            old_config = self._current
            new_config = self._load_from_disk()
            self._current = new_config
            self._last_written_version = version
            await self._notify_subscribers(old_config, new_config, source="file")
            return new_config

    async def save(self) -> None:
        """将当前快照持久化到磁盘。"""

        async with self._lock:
            self._persist_snapshot(self._current)

    def update(self, **changes: Any) -> ConfigT:
        """显式更新配置快照。"""

        old_config, new_config = self._apply_changes(changes)
        self._schedule_notify(old_config, new_config, source="memory")
        return new_config

    def subscribe(self, callback: ConfigSubscriber[ConfigT]) -> None:
        """注册配置校验通过后的变更回调。"""

        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: ConfigSubscriber[ConfigT]) -> None:
        """注销配置变更回调。"""

        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _load_from_disk(self) -> ConfigT:
        data = self._store.load_dict(self._path)
        try:
            return self._model_type.model_validate(data)
        except ValidationError as exc:
            raise ConfigValidationError(f"配置校验失败: {self._path}") from exc

    def _persist_snapshot(self, config: ConfigT) -> None:
        self._store.save_dict(self._path, config.model_dump(mode="json", exclude_none=True))
        self._last_written_version = self._store.get_version(self._path)

    def _apply_changes(self, changes: dict[str, Any]) -> tuple[ConfigT, ConfigT]:
        old_config = self._current
        new_config = self._build_updated_snapshot(old_config, changes)
        self._current = new_config
        return old_config, new_config

    def _build_updated_snapshot(self, current: ConfigT, changes: dict[str, Any]) -> ConfigT:
        merged_data = current.model_dump(mode="python")
        merged_data.update(changes)
        try:
            return self._model_type.model_validate(merged_data)
        except ValidationError as exc:
            raise ConfigValidationError("配置更新校验失败") from exc

    def _schedule_notify(
        self,
        old_config: ConfigT,
        new_config: ConfigT,
        source: ConfigSource,
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._notify_subscribers(old_config, new_config, source=source))

    async def _notify_subscribers(
        self,
        old_config: ConfigT,
        new_config: ConfigT,
        source: ConfigSource,
    ) -> None:
        changed_fields = tuple(
            field_name
            for field_name in self._model_type.model_fields
            if getattr(old_config, field_name) != getattr(new_config, field_name)
        )
        if not changed_fields:
            return

        event = ConfigChangeEvent[ConfigT](
            old_config=old_config,
            new_config=new_config,
            changed_fields=changed_fields,
            source=source,
        )
        for subscriber in tuple(self._subscribers):
            result = subscriber(event)
            if inspect.isawaitable(result):
                await result

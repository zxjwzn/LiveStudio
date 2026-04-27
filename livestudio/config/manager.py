"""核心配置管理器。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

import json5
import yaml
from pydantic import BaseModel, ValidationError

from .errors import (
    ConfigFormatError,
    ConfigLoadError,
    ConfigSaveError,
    ConfigValidationError,
)

ConfigT = TypeVar("ConfigT", bound=BaseModel)
ConfigFormat = Literal["json", "yaml"]


class ConfigManager(Generic[ConfigT]):
    """管理经校验的配置快照，并提供显式保存语义。"""

    def __init__(
        self,
        model_type: type[ConfigT],
        path: str | Path,
        *,
        auto_create: bool = True,
    ) -> None:
        self._model_type = model_type
        self._path = Path(path)
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

    def _detect_format(self, path: Path) -> ConfigFormat:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix in {".yaml", ".yml"}:
            return "yaml"
        raise ConfigFormatError(f"不支持的配置文件格式: {path.suffix}")

    def _load_dict(self, path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ConfigLoadError(f"配置文件不存在: {path}") from exc
        except OSError as exc:
            raise ConfigLoadError(f"读取配置文件失败: {path}") from exc

        try:
            file_format = self._detect_format(path)
            data = json5.loads(text) if file_format == "json" else yaml.safe_load(text)
        except (ValueError, yaml.YAMLError) as exc:
            raise ConfigFormatError(f"配置文件格式错误: {path}") from exc

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ConfigFormatError("配置文件根节点必须是对象映射")
        return data

    def _save_dict(self, path: Path, data: dict[str, Any]) -> None:
        file_format = self._detect_format(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if file_format == "json":
            content = json.dumps(data, ensure_ascii=False, indent=2) + os.linesep
        else:
            content = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)

        temp_path = path.with_name(f"{path.name}.tmp")
        try:
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(path)
        except OSError as exc:
            raise ConfigSaveError(f"写入配置文件失败: {path}") from exc
        finally:
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()

    async def load(self) -> ConfigT:
        """从磁盘加载配置，或按默认值自动创建配置文件。"""

        async with self._lock:
            if self._path.exists():
                config = self._load_from_disk()
                self._current = config
                return config

            if not self._auto_create:
                raise ConfigLoadError(f"配置文件不存在: {self._path}")

            self._persist_snapshot(self._current)
            return self._current

    async def reload(self) -> ConfigT:
        """重新从磁盘加载配置。"""

        return await self.load()

    async def save(self) -> None:
        """将当前快照持久化到磁盘。"""

        async with self._lock:
            self._persist_snapshot(self._current)

    def _load_from_disk(self) -> ConfigT:
        data = self._load_dict(self._path)
        try:
            return self._model_type.model_validate(data)
        except ValidationError as exc:
            raise ConfigValidationError(f"配置校验失败: {self._path}") from exc

    def _persist_snapshot(self, config: ConfigT) -> None:
        self._save_dict(
            self._path,
            config.model_dump(mode="json", exclude_none=True),
        )

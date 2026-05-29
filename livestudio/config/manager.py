"""核心配置管理器。"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

import json5
import yaml
from pydantic import BaseModel, ValidationError

from livestudio.utils.log import logger

from .errors import (
    ConfigFormatError,
    ConfigLoadError,
    ConfigSaveError,
    ConfigValidationError,
)

ConfigT = TypeVar("ConfigT", bound=BaseModel)
ConfigFormat = Literal["json", "yaml"]

_MAX_TOLERANT_ATTEMPTS = 64


class ConfigManager(Generic[ConfigT]):
    """管理经校验的配置快照，并提供显式保存语义。

    支持宽容加载：先以默认配置补齐缺失字段；当配置文件中的字段不再被模型识别
    （字段被删除、重命名、类型变更、枚举值失效等）时，丢弃不兼容字段、保留其余可用部分；
    迁移成功后会先把原文件备份为 ``<name>.<timestamp>.bak``，再写回迁移后的配置。
    """

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
            content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
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
        return self._migrate_and_load(data)

    def _migrate_and_load(self, original_data: dict[str, Any]) -> ConfigT:
        default_data = self._model_type().model_dump(mode="json", exclude_none=True)
        cleaned: Any = _merge_defaults(default_data, original_data)
        dropped: list[tuple[str | int, ...]] = []
        defaults_added = cleaned != original_data

        for _ in range(_MAX_TOLERANT_ATTEMPTS):
            try:
                config = self._model_type.model_validate(cleaned)
            except ValidationError as exc:
                if not self._apply_one_fix(cleaned, default_data, exc, dropped):
                    raise ConfigValidationError(
                        f"配置校验失败且无法迁移: {self._path}",
                    ) from exc
                continue

            self._on_migrated(config, dropped, defaults_added=defaults_added)
            return config

        raise ConfigValidationError(
            f"配置迁移超过最大尝试次数: {self._path}",
        )

    @staticmethod
    def _apply_one_fix(
        data: Any,
        default_data: Any,
        error: ValidationError,
        dropped: list[tuple[str | int, ...]],
    ) -> bool:
        for entry in error.errors():
            loc = tuple(entry.get("loc", ()))
            if not loc:
                continue
            if entry.get("type", "") == "missing":
                # 必填字段缺失：模型本身没有默认值，无法靠丢弃修复，跳过该项继续看下一条。
                continue
            if _reset_to_default_at_path(data, default_data, loc):
                dropped.append(loc)
                return True
            if _delete_at_path(data, loc):
                dropped.append(loc)
                return True
        return False

    def _on_migrated(
        self,
        config: ConfigT,
        dropped: list[tuple[str | int, ...]],
        *,
        defaults_added: bool,
    ) -> None:
        if not dropped and not defaults_added:
            return

        if dropped:
            formatted = ", ".join(
                ".".join(str(part) for part in path) for path in dropped
            )
            logger.warning(
                "配置文件 {} 含有不兼容字段，已自动迁移并丢弃: {}",
                self._path,
                formatted,
            )
        if defaults_added:
            logger.warning("配置文件 {} 缺少默认字段，已自动补齐", self._path)

        try:
            self._backup_original()
        except OSError as exc:
            logger.warning("备份原配置文件失败 ({}): {}", self._path, exc)

        with contextlib.suppress(ConfigSaveError):
            self._persist_snapshot(config)

    def _backup_original(self) -> None:
        if not self._path.exists():
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self._path.with_name(
            f"{self._path.name}.{timestamp}.bak",
        )
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(self._path.read_bytes())
        logger.info("原配置文件已备份: {}", backup_path)

    def _persist_snapshot(self, config: ConfigT) -> None:
        self._save_dict(
            self._path,
            config.model_dump(mode="json", exclude_none=True),
        )


def _delete_at_path(data: Any, path: tuple[str | int, ...]) -> bool:
    """按 Pydantic loc 路径在 dict/list 嵌套结构中删除一个节点。"""

    if not path:
        return False
    cursor: Any = data
    for key in path[:-1]:
        if isinstance(cursor, dict):
            if key not in cursor:
                return False
            cursor = cursor[key]
            continue
        if isinstance(cursor, list) and isinstance(key, int):
            if key < 0 or key >= len(cursor):
                return False
            cursor = cursor[key]
            continue
        return False

    last = path[-1]
    if isinstance(cursor, dict):
        if last not in cursor:
            return False
        del cursor[last]
        return True
    if isinstance(cursor, list) and isinstance(last, int):
        if last < 0 or last >= len(cursor):
            return False
        del cursor[last]
        return True
    return False


def _merge_defaults(default_data: Any, loaded_data: Any) -> Any:
    """Deep-merge loaded config over defaults so missing fields are backfilled."""

    if isinstance(default_data, dict) and isinstance(loaded_data, dict):
        merged = copy.deepcopy(default_data)
        for key, value in loaded_data.items():
            if key in merged:
                merged[key] = _merge_defaults(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    return copy.deepcopy(loaded_data)


def _reset_to_default_at_path(
    data: Any,
    default_data: Any,
    path: tuple[str | int, ...],
) -> bool:
    """Reset a nested value to the current model default when available."""

    if not path:
        return False
    cursor: Any = data
    default_cursor: Any = default_data
    for key in path[:-1]:
        if isinstance(cursor, dict):
            if key not in cursor:
                return False
            cursor = cursor[key]
        elif isinstance(cursor, list) and isinstance(key, int):
            if key < 0 or key >= len(cursor):
                return False
            cursor = cursor[key]
        else:
            return False

        if isinstance(default_cursor, dict):
            if key not in default_cursor:
                return False
            default_cursor = default_cursor[key]
        elif isinstance(default_cursor, list) and isinstance(key, int):
            if key < 0 or key >= len(default_cursor):
                return False
            default_cursor = default_cursor[key]
        else:
            return False

    last = path[-1]
    if not isinstance(cursor, dict):
        return False
    if last not in cursor:
        return False
    if not isinstance(default_cursor, dict) or last not in default_cursor:
        return False
    cursor[last] = copy.deepcopy(default_cursor[last])
    return True

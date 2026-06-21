"""核心配置管理器"""

import asyncio
import contextlib
import json
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
    """管理配置快照，全项目唯一的配置读写契约。

    契约（不可协商，所有 config 都按此理解）：

    1. **文件即全部**：文件存在时，``load()`` 严格 ``model_validate`` 整份文件并
       替换内存快照，``default_config`` 被完全丢弃。**不做任何字段级合并**——
       文件里没有的字段只回落到 pydantic 模型自带的字段默认，不会从
       ``default_config`` 补字段。
    2. **默认仅用于首次创建**：文件不存在且 ``auto_create`` 为真时，用
       ``default_config or model_type()`` 落盘一次作为种子；此后该种子不再参与加载。
    3. **保存即快照**：``save()`` 把当前内存快照 ``model_dump`` 落盘，不读旧文件、
       不合并。

    推论：seed-once 内容（用户可增删的集合、平台相关默认）只能通过
    ``default_config`` 在首次创建时种入；运行时探测到的瞬态不应写进快照，
    否则会污染"用户意图"这一定位。详见 docs/config-framework-redesign.md。
    """

    def __init__(
        self,
        model_type: type[ConfigT],
        path: str | Path,
        *,
        auto_create: bool = True,
        default_config: ConfigT | None = None,
    ) -> None:
        self._model_type = model_type
        self._path = Path(path)
        self._auto_create = auto_create
        self._lock = asyncio.Lock()
        self._current = default_config or model_type()

    @property
    def config(self) -> ConfigT:
        """返回最新的已校验配置快照"""

        return self._current

    @property
    def path(self) -> Path:
        """返回配置文件路径"""

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
        """从磁盘加载配置，或按默认值自动创建配置文件"""

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
        """重新从磁盘加载配置"""

        return await self.load()

    async def save(self) -> None:
        """将当前快照持久化到磁盘"""

        async with self._lock:
            self._persist_snapshot(self._current)

    def _load_from_disk(self) -> ConfigT:
        data = self._load_dict(self._path)
        try:
            return self._model_type.model_validate(data)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(loc) for loc in error['loc']) or '<root>'}: {error['msg']}" for error in exc.errors()
            )
            raise ConfigValidationError(f"配置校验失败: {self._path} ({details})") from exc

    def _persist_snapshot(self, config: ConfigT) -> None:
        self._save_dict(
            self._path,
            config.model_dump(mode="json", exclude_none=True),
        )

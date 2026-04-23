"""配置文件加载与持久化辅助工具。"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any, Literal

import json5
import yaml

from .errors import ConfigFormatError, ConfigLoadError, ConfigSaveError

ConfigFormat = Literal["json", "yaml"]


class ConfigStore:
    """加载并持久化配置字典。"""

    def detect_format(self, path: Path) -> ConfigFormat:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return "json"
        if suffix in {".yaml", ".yml"}:
            return "yaml"
        raise ConfigFormatError(f"不支持的配置文件格式: {path.suffix}")

    def load_dict(self, path: Path) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ConfigLoadError(f"配置文件不存在: {path}") from exc
        except OSError as exc:
            raise ConfigLoadError(f"读取配置文件失败: {path}") from exc

        try:
            file_format = self.detect_format(path)
            data = json5.loads(text) if file_format == "json" else yaml.safe_load(text)
        except (ValueError, yaml.YAMLError) as exc:
            raise ConfigFormatError(f"配置文件格式错误: {path}") from exc

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ConfigFormatError("配置文件根节点必须是对象映射")
        return data

    def save_dict(self, path: Path, data: dict[str, Any]) -> None:
        file_format = self.detect_format(path)
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

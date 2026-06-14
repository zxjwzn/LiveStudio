"""扩展 ConfigManager 测试"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from livestudio.config.errors import ConfigFormatError, ConfigLoadError, ConfigValidationError
from livestudio.config.manager import ConfigManager


class _Inner(BaseModel):
    level: int = 1
    tag: str = "default"


class _TestConfig(BaseModel):
    name: str = "test"
    count: int = 10
    inner: _Inner = _Inner()
    items: list[str] = []


async def test_json_format_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    manager = ConfigManager(_TestConfig, path)

    config = await manager.load()
    config.name = "json-test"
    await manager.save()

    loaded = await ConfigManager(_TestConfig, path).load()
    assert loaded.name == "json-test"


async def test_unsupported_format_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.txt"
    manager = ConfigManager(_TestConfig, path)

    with pytest.raises(ConfigFormatError, match="不支持的配置文件格式"):
        await manager.load()


async def test_auto_create_false_raises_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    manager = ConfigManager(_TestConfig, path, auto_create=False)

    with pytest.raises(ConfigLoadError, match="配置文件不存在"):
        await manager.load()


async def test_empty_yaml_file_loads_defaults_without_rewriting(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    manager = ConfigManager(_TestConfig, path)

    config = await manager.load()

    assert config.name == "test"
    assert config.count == 10
    assert path.read_text(encoding="utf-8") == ""


async def test_reload_picks_up_disk_changes(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    manager = ConfigManager(_TestConfig, path)
    await manager.load()

    data = {"name": "reloaded", "count": 99, "inner": {"level": 1, "tag": "default"}, "items": ["a", "b"]}
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    config = await manager.reload()

    assert config.name == "reloaded"
    assert config.count == 99


async def test_invalid_existing_config_raises_without_rewriting(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    data = {
        "name": "ok",
        "count": "not_a_number",
        "inner": {"level": "bad", "tag": "fine"},
        "items": ["a", "b"],
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    manager = ConfigManager(_TestConfig, path)

    with pytest.raises(ConfigValidationError):
        await manager.load()

    assert yaml.safe_load(path.read_text(encoding="utf-8")) == data

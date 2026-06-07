"""扩展 ConfigManager 测试

覆盖：
- JSON 格式加载与保存
- 不支持的文件格式
- _merge_defaults 边界情况
- _reset_to_default_at_path 路径不存在
- _delete_at_path 列表索引
- 多次迁移（多个不兼容字段）
- reload 等价于 load
- auto_create=False 时文件不存在报错
- 空文件加载
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest
import yaml
from pydantic import BaseModel

from livestudio.config.manager import (
    ConfigManager,
    _delete_at_path,
    _merge_defaults,
    _reset_to_default_at_path,
)
from livestudio.config.errors import ConfigFormatError, ConfigLoadError


class _Inner(BaseModel):
    level: int = 1
    tag: str = "default"


class _TestConfig(BaseModel):
    name: str = "test"
    count: int = 10
    inner: _Inner = _Inner()
    items: list[str] = ["a", "b"]


# ── JSON 格式 ────────────────────────────────────────────────────────


async def test_json_format_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    manager = ConfigManager(_TestConfig, path)

    await manager.load()  # auto_create
    manager.config.name = "json-test"
    manager.config.count = 42
    await manager.save()

    manager2 = ConfigManager(_TestConfig, path)
    config = await manager2.load()

    assert config.name == "json-test"
    assert config.count == 42


# ── 不支持的格式 ─────────────────────────────────────────────────────


async def test_unsupported_format_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[section]\nkey = 1\n", encoding="utf-8")
    manager = ConfigManager(_TestConfig, path)

    with pytest.raises(ConfigFormatError, match="不支持的配置文件格式"):
        await manager.load()


# ── auto_create=False ────────────────────────────────────────────────


async def test_auto_create_false_raises_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    manager = ConfigManager(_TestConfig, path, auto_create=False)

    with pytest.raises(ConfigLoadError, match="配置文件不存在"):
        await manager.load()


# ── 空文件 ───────────────────────────────────────────────────────────


async def test_empty_yaml_file_loads_defaults(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    manager = ConfigManager(_TestConfig, path)

    config = await manager.load()

    assert config.name == "test"
    assert config.count == 10


# ── reload ───────────────────────────────────────────────────────────


async def test_reload_picks_up_disk_changes(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    manager = ConfigManager(_TestConfig, path)
    await manager.load()

    # 直接修改磁盘文件
    data = {"name": "reloaded", "count": 99, "inner": {"level": 1, "tag": "default"}, "items": ["a", "b"]}
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    config = await manager.reload()

    assert config.name == "reloaded"
    assert config.count == 99


# ── 多个不兼容字段迁移 ───────────────────────────────────────────────


async def test_multiple_invalid_fields_are_migrated(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    data = {
        "name": "ok",
        "count": "not_a_number",  # 类型错误
        "inner": {"level": "bad", "tag": "fine"},  # 嵌套类型错误
        "items": ["a", "b"],
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    manager = ConfigManager(_TestConfig, path)
    config = await manager.load()

    assert config.name == "ok"
    assert config.count == 10  # 回退到默认值
    assert config.inner.level == 1  # 回退到默认值
    assert config.inner.tag == "fine"  # 保留有效值


# ── _merge_defaults ──────────────────────────────────────────────────


def test_merge_defaults_fills_missing_keys() -> None:
    default = {"a": 1, "b": {"x": 10, "y": 20}}
    loaded = {"a": 2}
    result = _merge_defaults(default, loaded)

    assert result["a"] == 2
    assert result["b"] == {"x": 10, "y": 20}


def test_merge_defaults_preserves_extra_keys() -> None:
    default = {"a": 1}
    loaded = {"a": 2, "extra": "value"}
    result = _merge_defaults(default, loaded)

    assert result["a"] == 2
    assert result["extra"] == "value"


def test_merge_defaults_non_dict_loaded_returns_loaded() -> None:
    default = {"a": 1}
    loaded = "just a string"
    result = _merge_defaults(default, loaded)

    assert result == "just a string"


def test_merge_defaults_deep_merge() -> None:
    default = {"a": {"b": {"c": 1, "d": 2}}}
    loaded = {"a": {"b": {"c": 99}}}
    result = _merge_defaults(default, loaded)

    assert result["a"]["b"]["c"] == 99
    assert result["a"]["b"]["d"] == 2


# ── _delete_at_path ──────────────────────────────────────────────────


def test_delete_at_path_dict() -> None:
    data = {"a": {"b": 1, "c": 2}}
    assert _delete_at_path(data, ("a", "b"))
    assert data == {"a": {"c": 2}}


def test_delete_at_path_list_index() -> None:
    data = {"items": [10, 20, 30]}
    assert _delete_at_path(data, ("items", 1))
    assert data == {"items": [10, 30]}


def test_delete_at_path_nonexistent_returns_false() -> None:
    data = {"a": 1}
    assert not _delete_at_path(data, ("b",))


def test_delete_at_path_empty_path_returns_false() -> None:
    data = {"a": 1}
    assert not _delete_at_path(data, ())


def test_delete_at_path_list_out_of_range() -> None:
    data = {"items": [1, 2]}
    assert not _delete_at_path(data, ("items", 5))


# ── _reset_to_default_at_path ────────────────────────────────────────


def test_reset_to_default_at_path_success() -> None:
    data = {"a": {"b": "bad"}}
    default = {"a": {"b": "good"}}
    assert _reset_to_default_at_path(data, default, ("a", "b"))
    assert data["a"]["b"] == "good"


def test_reset_to_default_at_path_missing_in_default() -> None:
    data = {"a": {"b": "bad"}}
    default = {"a": {}}
    assert not _reset_to_default_at_path(data, default, ("a", "b"))


def test_reset_to_default_at_path_empty_path() -> None:
    data = {"a": 1}
    default = {"a": 2}
    assert not _reset_to_default_at_path(data, default, ())

"""测试 ConfigManager"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, Field

from livestudio.config import ConfigLoadError, ConfigManager, ConfigValidationError


class _ChildConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: float = Field(default=0.5)


class _RootConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="default")
    child: _ChildConfig = Field(default_factory=_ChildConfig)


async def test_load_creates_default_when_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.yaml"
    manager = ConfigManager(_RootConfig, config_path)

    config = await manager.load()

    assert config.name == "default"
    assert config_path.exists()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw == {"name": "default", "child": {"threshold": 0.5}}


async def test_load_existing_file_is_strict(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "name": "kept",
                "child": {"threshold": 0.9, "obsolete_flag": True},
            },
        ),
        encoding="utf-8",
    )

    manager = ConfigManager(_RootConfig, config_path)

    with pytest.raises(ConfigValidationError):
        await manager.load()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["child"]["obsolete_flag"] is True


async def test_load_existing_file_uses_model_defaults_without_rewriting(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.yaml"
    config_path.write_text(yaml.safe_dump({"child": {}}, sort_keys=False), encoding="utf-8")

    manager = ConfigManager(_RootConfig, config_path)
    config = await manager.load()

    assert config.name == "default"
    assert config.child.threshold == 0.5
    assert yaml.safe_load(config_path.read_text(encoding="utf-8")) == {"child": {}}


async def test_load_invalid_value_raises_without_rewriting(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.yaml"
    config_path.write_text(
        yaml.safe_dump({"name": "kept", "child": {"threshold": "bad"}}),
        encoding="utf-8",
    )

    manager = ConfigManager(_RootConfig, config_path)

    with pytest.raises(ConfigValidationError):
        await manager.load()

    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["child"]["threshold"] == "bad"


async def test_save_roundtrip(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.yaml"
    manager = ConfigManager(_RootConfig, config_path)

    await manager.load()
    manager.config.name = "updated"
    manager.config.child.threshold = 0.75
    await manager.save()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw == {"name": "updated", "child": {"threshold": 0.75}}


async def test_load_raises_when_auto_create_disabled(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.yaml"
    manager = ConfigManager(_RootConfig, config_path, auto_create=False)

    with pytest.raises(ConfigLoadError):
        await manager.load()

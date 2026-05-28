"""ConfigManager 测试。

覆盖：
- 自动创建默认配置文件
- 容错迁移：丢弃不兼容字段、备份原文件
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, Field

from livestudio.config import ConfigManager


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
    assert config_path.exists(), "缺失时应自动落盘默认配置"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw == {"name": "default", "child": {"threshold": 0.5}}


async def test_load_migrates_dropping_unknown_fields(tmp_path: Path) -> None:
    config_path = tmp_path / "cfg.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "name": "kept",
                "child": {"threshold": 0.9, "obsolete_flag": True},
                "removed_top_level": 42,
            },
        ),
        encoding="utf-8",
    )

    manager = ConfigManager(_RootConfig, config_path)
    config = await manager.load()

    assert config.name == "kept"
    assert config.child.threshold == 0.9

    backups = list(config_path.parent.glob(f"{config_path.name}.*.bak"))
    assert len(backups) == 1, "迁移后应留有一份原文件备份"

    rewritten = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "removed_top_level" not in rewritten
    assert "obsolete_flag" not in rewritten["child"]


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

    from livestudio.config import ConfigLoadError

    with pytest.raises(ConfigLoadError):
        await manager.load()

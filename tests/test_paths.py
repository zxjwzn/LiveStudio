"""测试文件路径小工具"""

from __future__ import annotations

from livestudio.utils.paths import (
    CONFIG_DIR,
    PROJECT_ROOT,
    config_path,
    resolve_config_path,
)


def test_default_config_dir_is_project_configs() -> None:
    assert CONFIG_DIR == PROJECT_ROOT / "configs"
    assert (
        config_path("vtube_studio.yaml")
        == PROJECT_ROOT / "configs" / "vtube_studio.yaml"
    )


def test_resolve_config_path_keeps_configs_relative_to_project_root() -> None:
    assert resolve_config_path("models/vtubestudio") == (
        PROJECT_ROOT / "configs" / "models" / "vtubestudio"
    )
    assert resolve_config_path("configs/models/vtubestudio") == (
        PROJECT_ROOT / "configs" / "models" / "vtubestudio"
    )

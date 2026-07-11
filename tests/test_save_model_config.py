"""测试 VTube Studio 模型配置保存:内存快照与文件同步,重连不覆盖编辑

回归平台页编辑模型配置后的两个问题:
1. 保存只写盘,不更新程序内 ``model_config`` 变量(滞后);
2. 重连走 ``_do_stop`` 把滞后内存快照写回盘,覆盖用户编辑,文件恢复原样。

修复后:保存经 ``VTubeStudio.save_model_config`` -> ``PlatformModelConfigService.save_to``,
编辑当前模型时同步内存快照(单源事实)再落盘,使停机 ``save()`` 不再覆盖。
"""

# ruff: noqa: SLF001

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from livestudio.services.platforms.model import PlatformModelIdentity
from livestudio.services.platforms.vtubestudio import VTubeStudio, VTubeStudioModelConfig


def _load_raw(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _with_blink_disabled(config: VTubeStudioModelConfig) -> VTubeStudioModelConfig:
    """返回一份仅把 blink.enabled 置 False 的深拷贝(模拟用户在配置页编辑)"""

    return config.model_copy(
        update={
            "controllers": config.controllers.model_copy(
                update={
                    "blink": config.controllers.blink.model_copy(update={"enabled": False}),
                },
            ),
        },
    )


@pytest.fixture
def platform(tmp_path: Path) -> VTubeStudio:
    """已注入假 client 的 VTube Studio:reload_model_config 可直接调用,无需 start()"""

    p = VTubeStudio()
    p.config.model_config_dir = str(tmp_path)
    # client 仅用于 _ensure_plugin_parameters / _refresh_parameter_specs,二者均 try/except
    # 兜底;让 get_input_parameters 抛错使参数规格刷新提前返回,聚焦保存/同步逻辑。
    p._client = AsyncMock()
    p._client.get_input_parameters.side_effect = RuntimeError("no client")
    return p


async def test_save_model_config_updates_in_memory_snapshot(platform: VTubeStudio) -> None:
    """保存当前模型配置:程序内 model_config 变量实时覆盖为编辑后的快照"""

    await platform.reload_model_config("model-1", "avatar")
    original = platform.model_config
    assert original.controllers.blink.enabled is True

    edited = _with_blink_disabled(original)
    await platform.save_model_config(platform.model_config_manager.path, edited)

    # 程序内 config 变量已实时覆盖
    assert platform.model_config is edited
    assert platform.model_config.controllers.blink.enabled is False


async def test_save_model_config_survives_stop_save(platform: VTubeStudio) -> None:
    """保存后模拟重连路径上 _do_stop 的 model_config_service.save():文件不被恢复原样"""

    await platform.reload_model_config("model-1", "avatar")
    original = platform.model_config
    await platform.save_model_config(
        platform.model_config_manager.path,
        _with_blink_disabled(original),
    )

    # 模拟 _do_stop:用(已同步的)内存快照落盘--修复前此处会用滞后旧快照覆盖编辑
    await platform.model_config_manager.save()

    assert _load_raw(platform.model_config_manager.path)["controllers"]["blink"]["enabled"] is False


async def test_save_model_config_survives_reload(platform: VTubeStudio) -> None:
    """保存后重连(reload_model_config 重新从文件读):编辑持久存在"""

    await platform.reload_model_config("model-1", "avatar")
    original = platform.model_config
    await platform.save_model_config(
        platform.model_config_manager.path,
        _with_blink_disabled(original),
    )

    await platform.reload_model_config("model-1", "avatar")

    assert platform.model_config.controllers.blink.enabled is False


async def test_save_model_config_unconnected_only_writes_file(tmp_path: Path) -> None:
    """未连接(无已加载模型)时保存:仅落盘,不抛错"""

    p = VTubeStudio()
    p.config.model_config_dir = str(tmp_path)
    identity_path = tmp_path / "avatar_model.yaml"
    config = VTubeStudioModelConfig.create_default(
        PlatformModelIdentity(
            platform_name="vtubestudio",
            model_id="model-1",
            model_name="avatar",
        ),
    )
    edited = _with_blink_disabled(config)

    await p.save_model_config(identity_path, edited)

    assert identity_path.exists()
    assert _load_raw(identity_path)["controllers"]["blink"]["enabled"] is False


async def test_save_model_config_other_path_leaves_current_untouched(
    platform: VTubeStudio,
) -> None:
    """编辑非当前模型:仅落盘该文件,当前模型内存快照与文件均不受影响"""

    await platform.reload_model_config("model-1", "avatar")
    current_path = platform.model_config_manager.path
    original = platform.model_config
    assert original.controllers.blink.enabled is True

    other_path = current_path.parent / "other_model.yaml"
    await platform.save_model_config(other_path, _with_blink_disabled(original))

    # 当前模型内存快照未变
    assert platform.model_config.controllers.blink.enabled is True
    # 另一文件已落盘,当前文件未被动
    assert _load_raw(other_path)["controllers"]["blink"]["enabled"] is False
    assert _load_raw(current_path)["controllers"]["blink"]["enabled"] is True

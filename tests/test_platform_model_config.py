"""测试不同平台共用的模型配置服务"""

from __future__ import annotations

from pathlib import Path

from livestudio.config import ConfigManager
from livestudio.services.platforms import (
    PlatformModelConfig,
    PlatformModelConfigService,
    PlatformModelIdentity,
)


def _identity() -> PlatformModelIdentity:
    return PlatformModelIdentity(
        platform_name="test-platform",
        model_id="model/id:*",
        model_name="测试 Model",
    )


def _with_blink_disabled(config: PlatformModelConfig) -> PlatformModelConfig:
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


async def test_platform_model_config_service_creates_default_file(
    tmp_path,
) -> None:
    service = PlatformModelConfigService(
        config_model=PlatformModelConfig,
        model_config_dir=str(tmp_path),
    )

    config = await service.load(_identity())

    assert config.model.platform_name == "test-platform"
    assert config.model.model_id == "model/id:*"
    assert config.controllers.blink.enabled
    assert service.manager is not None
    assert service.manager.path.exists()
    assert service.manager.path.name == "测试_Model_model.yaml"


async def test_platform_model_config_service_updates_existing_new_identity(
    tmp_path,
) -> None:
    service = PlatformModelConfigService(
        config_model=PlatformModelConfig,
        model_config_dir=str(tmp_path),
    )
    await service.load(
        PlatformModelIdentity(
            platform_name="legacy",
            model_id="legacy-id",
            model_name="Legacy",
        ),
    )
    await service.save()

    config = await service.load(
        PlatformModelIdentity(
            platform_name="legacy",
            model_id="legacy-id",
            model_name="Legacy",
        ),
    )

    assert config.model.platform_name == "legacy"
    assert config.model.model_id == "legacy-id"
    assert config.model.model_name == "Legacy"


async def test_config_property_is_single_source_with_manager(tmp_path: Path) -> None:
    """config 派生自 manager.config:未加载为 None,加载后与 manager 快照同一对象"""

    service = PlatformModelConfigService(
        config_model=PlatformModelConfig,
        model_config_dir=str(tmp_path),
    )
    assert service.config is None

    config = await service.load(_identity())

    assert service.manager is not None
    assert service.config is service.manager.config
    assert service.config is config


async def test_save_to_current_path_syncs_in_memory_and_file(tmp_path: Path) -> None:
    """save_to 当前模型路径:替换内存快照(单源)再落盘,内存与文件一致"""

    service = PlatformModelConfigService(
        config_model=PlatformModelConfig,
        model_config_dir=str(tmp_path),
    )
    original = await service.load(_identity())
    assert service.manager is not None
    current_path = service.manager.path
    assert original.controllers.blink.enabled is True

    edited = _with_blink_disabled(original)
    await service.save_to(current_path, edited)

    # 内存快照已同步为编辑后的实例
    assert service.config is edited
    assert edited.controllers.blink.enabled is False
    # 文件已落盘为新快照
    reloaded = await ConfigManager(PlatformModelConfig, current_path).load()
    assert reloaded.controllers.blink.enabled is False


async def test_save_to_current_path_survives_subsequent_save(tmp_path: Path) -> None:
    """save_to 后再 save()(模拟停机)不会用旧快照覆盖:文件保持编辑后的值"""

    service = PlatformModelConfigService(
        config_model=PlatformModelConfig,
        model_config_dir=str(tmp_path),
    )
    original = await service.load(_identity())
    assert service.manager is not None
    current_path = service.manager.path

    await service.save_to(current_path, _with_blink_disabled(original))
    # 模拟 _do_stop 的 service.save():用已同步的内存快照落盘
    await service.save()

    reloaded = await ConfigManager(PlatformModelConfig, current_path).load()
    assert reloaded.controllers.blink.enabled is False


async def test_save_to_other_path_leaves_current_snapshot_untouched(tmp_path: Path) -> None:
    """save_to 非当前模型路径:仅落盘该文件,不改动当前模型内存快照与文件"""

    service = PlatformModelConfigService(
        config_model=PlatformModelConfig,
        model_config_dir=str(tmp_path),
    )
    original = await service.load(_identity())
    assert service.manager is not None
    current_path = service.manager.path

    other_path = tmp_path / "other_model.yaml"
    await service.save_to(other_path, _with_blink_disabled(original))

    # 当前模型内存快照未受影响
    assert service.config is original
    assert original.controllers.blink.enabled is True
    # 另一文件已落盘,当前文件未被动
    other_reloaded = await ConfigManager(PlatformModelConfig, other_path).load()
    assert other_reloaded.controllers.blink.enabled is False
    current_reloaded = await ConfigManager(PlatformModelConfig, current_path).load()
    assert current_reloaded.controllers.blink.enabled is True

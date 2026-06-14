"""测试不同平台共用的模型配置服务"""

from __future__ import annotations

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

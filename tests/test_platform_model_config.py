"""测试不同平台共用的模型配置服务"""

from __future__ import annotations

from livestudio.services.platforms import (
    PlatformModelConfig,
    PlatformModelConfigService,
    PlatformModelIdentity,
)
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticAction,
    SemanticActionBinding,
)


def _identity() -> PlatformModelIdentity:
    return PlatformModelIdentity(
        platform_name="test-platform",
        model_id="model/id:*",
        model_name="测试 Model",
    )


async def test_platform_model_config_service_loads_and_backfills_defaults(
    tmp_path,
) -> None:
    service = PlatformModelConfigService(
        config_model=PlatformModelConfig,
        model_config_dir=str(tmp_path),
        default_bindings=(
            SemanticActionBinding(
                action=SemanticAction.MOUTH_OPEN.value,
                platform_params=["JawOpen"],
            ),
        ),
        default_parameter_specs=(
            PlatformParameterSpec(
                name="JawOpen",
                minimum=0.0,
                maximum=1.0,
                neutral=0.0,
                default=0.0,
            ),
        ),
    )

    config = await service.load(_identity())

    assert config.model.platform_name == "test-platform"
    assert config.model.model_id == "model/id:*"
    assert config.semantic_profile.model_id == "model/id:*"
    assert SemanticAction.MOUTH_OPEN.value in config.semantic_profile.bindings
    assert [spec.name for spec in config.parameter_specs] == ["JawOpen"]
    assert config.controllers.blink.enabled
    assert service.manager is not None
    assert service.manager.path.exists()
    assert service.manager.path.name == "测试_Model_model_id.yaml"


async def test_platform_model_config_service_updates_existing_new_identity(
    tmp_path,
) -> None:
    service = PlatformModelConfigService(
        config_model=PlatformModelConfig,
        model_config_dir=str(tmp_path),
    )
    original = await service.load(
        PlatformModelIdentity(
            platform_name="legacy",
            model_id="legacy-id",
            model_name="Legacy",
        ),
    )
    original.semantic_profile.model_id = "stale"
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

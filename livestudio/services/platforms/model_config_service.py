"""读取和保存跨平台模型配置的服务"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Generic, TypeVar

from livestudio.config import ConfigManager
from livestudio.services.semantic_actions import (
    PlatformParameterSpec,
    SemanticActionBinding,
)
from livestudio.utils.paths import resolve_config_path

from .model import PlatformModelIdentity
from .model_config import PlatformModelConfig

ModelConfigT = TypeVar("ModelConfigT", bound=PlatformModelConfig)


class PlatformModelConfigService(Generic[ModelConfigT]):
    """读取、整理、补齐并保存每个模型的平台配置"""

    def __init__(
        self,
        *,
        config_model: type[ModelConfigT],
        model_config_dir: str,
        default_bindings: Iterable[SemanticActionBinding] = (),
        default_parameter_specs: Iterable[PlatformParameterSpec] = (),
    ) -> None:
        self.config_model = config_model
        self.model_config_dir = model_config_dir
        self.default_bindings = tuple(default_bindings)
        self.default_parameter_specs = tuple(default_parameter_specs)
        self.manager: ConfigManager[ModelConfigT] | None = None
        self.config: ModelConfigT | None = None
        self.identity: PlatformModelIdentity | None = None

    async def load(self, identity: PlatformModelIdentity) -> ModelConfigT:
        """读取或创建某个平台模型的配置"""

        config_path = self.build_path(identity)
        manager = ConfigManager(self.config_model, config_path)
        config = await manager.reload()
        changed = self.apply_defaults(config, identity)
        if changed:
            await manager.save()
        self.manager = manager
        self.config = config
        self.identity = identity
        return config

    async def save(self) -> None:
        """如果当前模型配置已经加载，就保存它"""

        if self.manager is not None:
            await self.manager.save()

    def apply_defaults(
        self,
        config: ModelConfigT,
        identity: PlatformModelIdentity,
    ) -> bool:
        """同步模型身份和平台提供的默认对应关系"""

        changed = config.sync_identity(identity)
        changed = config.ensure_semantic_profile_defaults(self.default_bindings) or changed
        changed = config.ensure_parameter_spec_defaults(self.default_parameter_specs) or changed
        return config.ensure_expression_profile_defaults() or changed

    def build_path(self, identity: PlatformModelIdentity) -> Path:
        """返回某个平台模型对应的配置路径"""

        safe_name = self.sanitize_path_part(identity.model_name)
        safe_id = self.sanitize_path_part(identity.model_id)
        return resolve_config_path(self.model_config_dir) / f"{safe_name}_{safe_id}.yaml"

    @staticmethod
    def sanitize_path_part(value: str) -> str:
        """清理模型身份里的某一段，让它能安全放进配置文件名"""

        sanitized = re.sub(r"[^a-zA-Z0-9_.\-\u4e00-\u9fff]+", "_", value).strip(
            " ._",
        )
        return sanitized or "unknown"

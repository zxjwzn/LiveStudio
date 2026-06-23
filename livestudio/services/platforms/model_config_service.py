"""读取和保存跨平台模型配置的服务"""

import re
from typing import Generic, TypeVar

from livestudio.config import ConfigManager
from livestudio.utils.paths import resolve_config_path

from .model import PlatformModelConfig, PlatformModelIdentity

ModelConfigT = TypeVar("ModelConfigT", bound=PlatformModelConfig)


class PlatformModelConfigService(Generic[ModelConfigT]):
    """读取或创建每个模型的平台配置"""

    def __init__(
        self,
        *,
        config_model: type[ModelConfigT],
        model_config_dir: str,
    ) -> None:
        self.config_model = config_model
        self.model_config_dir = model_config_dir
        self.manager: ConfigManager[ModelConfigT] | None = None
        self.config: ModelConfigT | None = None
        self.identity: PlatformModelIdentity | None = None

    async def load(self, identity: PlatformModelIdentity) -> ModelConfigT:
        """读取或创建某个平台模型的配置"""

        safe_name = self.sanitize_path_part(identity.model_name)
        safe_id = self.sanitize_path_part(identity.model_id)[:5]
        config_path = resolve_config_path(self.model_config_dir) / f"{safe_name}_{safe_id}.yaml"
        default_config = self.config_model.create_default(identity)
        manager = ConfigManager(
            self.config_model,
            config_path,
            default_config=default_config,
        )
        config = await manager.load()
        self.manager = manager
        self.config = config
        self.identity = identity
        return config

    async def save(self) -> None:
        """如果当前模型配置已经加载，就保存它"""

        if self.manager is not None:
            await self.manager.save()

    @staticmethod
    def sanitize_path_part(value: str) -> str:
        """清理模型身份里的某一段，让它能安全放进配置文件名"""

        sanitized = re.sub(r"[^a-zA-Z0-9_.\-\u4e00-\u9fff]+", "_", value).strip(
            " ._",
        )
        return sanitized or "unknown"

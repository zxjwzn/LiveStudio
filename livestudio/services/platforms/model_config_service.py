"""读取和保存跨平台模型配置的服务"""

import re
from pathlib import Path
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
        self.identity: PlatformModelIdentity | None = None

    @property
    def config(self) -> ModelConfigT | None:
        """当前模型配置快照(单源:即底层 manager 的内存快照)。

        派生自 ``manager.config`` 而非独立字段,使外部经 ``save_to()`` 替换 manager 快照后
        本属性即时反映新值,避免「内存快照滞后于文件」--此前独立字段与 manager 快照各持一份
        引用,外部写盘不更新字段,导致停机 ``save()`` 用滞后字段覆盖用户编辑。
        """

        return self.manager.config if self.manager is not None else None

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
        self.identity = identity
        return config

    async def save(self) -> None:
        """如果当前模型配置已经加载，就保存它"""

        if self.manager is not None:
            await self.manager.save()

    async def save_to(self, path: Path, config: ModelConfigT) -> None:
        """保存配置到指定路径;若为当前模型配置路径,先同步内存快照再落盘。

        同步内存快照(经 ``manager.save(config)`` 替换 manager 的内存快照)使 ``config`` 属性
        与文件一致,避免后续 ``save()``(如停机)用滞后快照覆盖外部编辑。非当前模型路径仅落盘
        --其内存快照属另一模型,而停机只保存当前模型,故无覆盖风险。
        """

        if self.manager is not None and self.manager.path == path:
            await self.manager.save(config)
        else:
            manager = ConfigManager(self.config_model, path, default_config=config)
            await manager.save()

    @staticmethod
    def sanitize_path_part(value: str) -> str:
        """清理模型身份里的某一段，让它能安全放进配置文件名"""

        sanitized = re.sub(r"[^a-zA-Z0-9_.\-\u4e00-\u9fff]+", "_", value).strip(
            " ._",
        )
        return sanitized or "unknown"

"""VTube Studio 子服务抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from livestudio.config import ConfigManager

if TYPE_CHECKING:
    from .service import VTubeStudio

ConfigT = TypeVar("ConfigT", bound=BaseModel)
FileConfigT = TypeVar("FileConfigT", bound="SubserviceConfigFile[Any]")


class SubserviceConfigFile(BaseModel, Generic[ConfigT]):
    """子服务独立配置文件基类。"""

    model_config = ConfigDict(extra="forbid")

    enable: bool = Field(default=True, description="是否启用当前子服务。")
    config: ConfigT


class VTubeStudioSubservice(ABC, Generic[FileConfigT]):
    """所有 VTube Studio 子服务的统一抽象。"""

    def __init__(
        self,
        name: str,
        config_model: type[FileConfigT],
        *,
        config_path: str | Path | None = None,
    ) -> None:
        self._name = name
        self._config_model = config_model
        self._config_path = Path(config_path) if config_path is not None else None
        self._config_manager: ConfigManager[FileConfigT] | None = None
        self._owner: VTubeStudio | None = None

    @property
    def name(self) -> str:
        """返回子服务名称。"""

        return self._name

    @property
    def config_model(self) -> type[FileConfigT]:
        """返回子服务配置文件模型类型。"""

        return self._config_model

    @property
    def config_path(self) -> Path | None:
        """返回显式指定的配置文件路径。"""

        return self._config_path

    @property
    def vtubestudio(self) -> VTubeStudio:
        """返回所属的 VTube Studio 服务实例。"""

        owner = self._owner
        if owner is None:
            raise RuntimeError(f"子服务 {self.name} 尚未绑定到 VTubeStudio")
        return owner

    @property
    def config_manager(self) -> ConfigManager[FileConfigT]:
        """返回子服务配置管理器。"""

        manager = self._config_manager
        if manager is None:
            raise RuntimeError(f"子服务 {self.name} 尚未初始化配置管理器")
        return manager

    @property
    def file_config(self) -> FileConfigT:
        """返回子服务完整配置文件快照。"""

        return self.config_manager.config

    @property
    def enabled(self) -> bool:
        """返回子服务启用状态。"""

        return self.file_config.enable

    def bind(self, owner: VTubeStudio, config_manager: ConfigManager[FileConfigT]) -> None:
        """绑定所属服务及配置管理器。"""

        self._owner = owner
        self._config_manager = config_manager

    async def initialize(self) -> None:
        """子服务初始化钩子。"""

    @abstractmethod
    async def start(self) -> None:
        """启动子服务。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止子服务。"""

    async def close(self) -> None:
        """关闭子服务。默认等同于停止。"""

        await self.stop()

    async def save_config(self) -> None:
        """持久化子服务配置。"""

        manager = self._config_manager
        if manager is not None:
            await manager.save()
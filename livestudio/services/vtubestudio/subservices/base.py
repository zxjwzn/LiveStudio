"""VTube Studio 子服务抽象。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from livestudio.config import ConfigManager
from livestudio.services.audio_stream.base import AudioStreamSource

if TYPE_CHECKING:
    from ..service import VTubeStudio

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
        config_path: str | Path,
    ) -> None:
        self._name = name
        self._config_model = config_model
        self.config_manager = ConfigManager(
            config_model,
            config_path,
        )
        self.audio_stream: AudioStreamSource | None = None
        self.owner: VTubeStudio | None = None

    @property
    def name(self) -> str:
        """返回子服务名称。"""

        return self._name

    @property
    def vtubestudio(self) -> VTubeStudio:
        """返回所属的 VTube Studio 服务实例。"""

        if self.owner is None:
            raise RuntimeError(f"子服务 {self.name} 尚未绑定到 VTubeStudio")
        return self.owner

    @property
    def config(self) -> FileConfigT:
        """返回子服务配置文件快照。"""

        return self.config_manager.config

    @property
    def enabled(self) -> bool:
        """返回子服务启用状态。"""

        return self.config_manager.config.enable

    @abstractmethod
    async def initialize(self) -> None:
        """子服务初始化钩子。"""

    @abstractmethod
    async def start(self) -> None:
        """启动子服务。"""

    @abstractmethod
    async def stop(self) -> None:
        """停止子服务。"""

    @abstractmethod
    async def close(self) -> None:
        """关闭子服务。默认等同于停止。"""

        await self.stop()

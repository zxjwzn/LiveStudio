"""用于配置管理的类型化模型。"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

ConfigT = TypeVar("ConfigT", bound=BaseModel)
ConfigSource = Literal["file", "memory"]


class FileVersion(BaseModel):
    """用于抑制自身触发重载循环的文件版本元数据。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    modified_time_ns: int = Field(ge=0)
    size: int = Field(ge=0)


class ConfigChangeEvent(BaseModel, Generic[ConfigT]):
    """描述一次通过校验的配置变更。"""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    old_config: ConfigT
    new_config: ConfigT
    changed_fields: tuple[str, ...]
    source: ConfigSource

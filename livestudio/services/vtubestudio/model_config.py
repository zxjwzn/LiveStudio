"""VTube Studio 模型级配置与加载仓库。"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from livestudio.config import ConfigManager

from ...clients.vtube_studio.models.model import CurrentModelResponseData
from .subservices.animation_runtime.models import ModelAnimationConfig
from .subservices.model_expression_sync.models import ManagedExpressionConfig

INVALID_WINDOWS_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*]')
MODEL_CONFIG_DIR = Path("config") / "models"


class ManagedModelConfig(BaseModel):
    """单个 VTube Studio 模型的持久化配置。"""

    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(
        default="UnknownModel",
        min_length=1,
        description="模型名称。",
    )
    model_id: str = Field(
        default="UnknownModelID",
        min_length=1,
        description="模型 ID。",
    )
    expressions: list[ManagedExpressionConfig] = Field(
        default_factory=list,
        description="该模型的表情激活配置。",
    )
    animation: ModelAnimationConfig = Field(
        default_factory=ModelAnimationConfig,
        description="该模型的动画控制器配置。",
    )


def sanitize_model_config_filename_part(value: str) -> str:
    """替换 Windows 非法文件名字符。"""

    sanitized = INVALID_WINDOWS_FILENAME_CHARS.sub("_", value).strip()
    return sanitized or "UnknownModel"


def build_model_config_path(model_name: str, model_id: str) -> Path:
    """根据模型名称和 ID 生成模型配置路径。"""

    safe_model_name = sanitize_model_config_filename_part(model_name)
    safe_model_id = sanitize_model_config_filename_part(model_id)
    return MODEL_CONFIG_DIR / f"{safe_model_name}_{safe_model_id}.yaml"


class VTubeStudioModelConfigRepository:
    """负责按当前 VTS 模型加载和创建模型级配置。"""

    async def load_current_model_config(
        self,
        current_model: CurrentModelResponseData,
    ) -> ConfigManager[ManagedModelConfig] | None:
        """加载当前模型配置；未加载模型时返回 None。"""

        if not current_model.model_loaded:
            return None

        return await self.load_model_config(
            model_name=current_model.model_name,
            model_id=current_model.model_id,
        )

    async def load_model_config(
        self,
        *,
        model_name: str,
        model_id: str,
    ) -> ConfigManager[ManagedModelConfig]:
        """加载指定模型配置，不存在时按默认结构创建。"""

        manager = ConfigManager(
            ManagedModelConfig,
            build_model_config_path(model_name, model_id),
        )
        if manager.path.exists():
            await manager.load()
        else:
            manager.config.model_name = model_name
            manager.config.model_id = model_id
            await manager.save()

        config_updated = False
        if manager.config.model_name != model_name:
            manager.config.model_name = model_name
            config_updated = True
        if manager.config.model_id != model_id:
            manager.config.model_id = model_id
            config_updated = True
        if config_updated:
            await manager.save()

        return manager

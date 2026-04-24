"""动画运行时子服务导出。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .models import (
    AnimationRuntimeConfig,
    AnimationRuntimeConfigFile,
    AnimationType,
    ModelAnimationConfig,
    MouthSyncControllerConfig,
)
from .template_repository import AnimationTemplateRepository, TemplateEvaluationError

if TYPE_CHECKING:
    from .service import AnimationRuntimeService


def __getattr__(name: str) -> Any:
    """惰性导出运行时服务，避免配置模型导入阶段产生循环依赖。"""

    if name == "AnimationRuntimeService":
        from .service import AnimationRuntimeService

        return AnimationRuntimeService
    raise AttributeError(name)

__all__ = [
    "AnimationRuntimeConfig",
    "AnimationRuntimeConfigFile",
    "AnimationRuntimeService",
    "AnimationTemplateRepository",
    "AnimationType",
    "ModelAnimationConfig",
    "MouthSyncControllerConfig",
    "TemplateEvaluationError",
]

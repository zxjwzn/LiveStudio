"""Platform-independent semantic action models and adapters."""

from .adapter import (
    CurveKind,
    PlatformParameterSpec,
    ResolvedPlatformParameter,
    SemanticActionAdapter,
    SemanticActionBinding,
    SemanticActionProfile,
    SemanticActionState,
)
from .models import (
    DEFAULT_SEMANTIC_ACTION_SPECS,
    SemanticAction,
    SemanticActionSpec,
    SemanticActionTarget,
    SemanticTweenRequest,
    clamp_semantic_value,
)

__all__ = [
    "DEFAULT_SEMANTIC_ACTION_SPECS",
    "CurveKind",
    "PlatformParameterSpec",
    "ResolvedPlatformParameter",
    "SemanticAction",
    "SemanticActionAdapter",
    "SemanticActionBinding",
    "SemanticActionProfile",
    "SemanticActionSpec",
    "SemanticActionState",
    "SemanticActionTarget",
    "SemanticTweenRequest",
    "clamp_semantic_value",
]

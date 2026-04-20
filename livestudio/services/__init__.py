"""应用服务层。"""

from .vtube_studio_service import (
    ManagedVTubeStudioService,
    build_managed_vtube_studio_service,
)

__all__ = ["ManagedVTubeStudioService", "build_managed_vtube_studio_service"]
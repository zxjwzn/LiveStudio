"""权限 API 请求/响应模型。"""

from __future__ import annotations

from pydantic import Field

from .base import VTSEmptyData, VTSRequestEnvelope, VTSResponseEnvelope


class Permission(VTSEmptyData):
    """单个权限状态。"""

    name: str = Field(description="权限名称。")
    granted: bool = Field(description="当前插件是否已获得该权限。")


class PermissionRequestData(VTSEmptyData):
    """权限请求负载。"""

    requested_permission: str | None = Field(
        default=None,
        alias="requestedPermission",
        description="要请求的权限名称；为空时仅查询当前权限列表。",
    )


class PermissionRequest(VTSRequestEnvelope[PermissionRequestData]):
    """权限请求。"""

    message_type: str = Field(default="PermissionRequest", alias="messageType", description="请求或查询插件权限。")
    data: PermissionRequestData = Field(default_factory=PermissionRequestData, description="权限请求参数。")


class PermissionResponseData(VTSEmptyData):
    """权限响应负载。"""

    grant_success: bool | None = Field(default=None, alias="grantSuccess", description="用户是否授予成功；纯查询时通常为空。")
    requested_permission: str | None = Field(default=None, alias="requestedPermission", description="本次请求的权限名称。")
    permissions: list[Permission] = Field(description="VTube Studio 当前提供的全部权限及授权状态。")


class PermissionResponse(VTSResponseEnvelope[PermissionResponseData]):
    """权限响应信封。"""
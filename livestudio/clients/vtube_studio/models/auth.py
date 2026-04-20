"""认证与通用会话状态的请求/响应模型。"""

from __future__ import annotations

from pydantic import Field

from .base import VTSEmptyData, VTSRequestEnvelope, VTSResponseEnvelope


class APIStateRequest(VTSRequestEnvelope[VTSEmptyData]):
    """查询 API 会话状态。"""

    message_type: str = Field(default="APIStateRequest", alias="messageType", description="请求当前 API 状态。")
    data: VTSEmptyData = Field(default_factory=VTSEmptyData, description="该请求无需额外参数。")


class APIStateResponseData(VTSEmptyData):
    """API 状态响应。"""

    active: bool = Field(description="API 服务当前是否激活。")
    v_tube_studio_version: str = Field(alias="vTubeStudioVersion", description="VTube Studio 版本号。")
    current_session_authenticated: bool = Field(alias="currentSessionAuthenticated", description="当前 WebSocket 会话是否已认证。")


class APIStateResponse(VTSResponseEnvelope[APIStateResponseData]):
    """API 状态响应信封。"""


class AuthenticationTokenRequestData(VTSEmptyData):
    """申请认证令牌。"""

    plugin_name: str = Field(alias="pluginName", min_length=3, max_length=32, description="插件名称。")
    plugin_developer: str = Field(alias="pluginDeveloper", min_length=3, max_length=32, description="插件开发者名称。")
    plugin_icon: str | None = Field(default=None, alias="pluginIcon", description="可选 128x128 Base64 图标。")


class AuthenticationTokenRequest(VTSRequestEnvelope[AuthenticationTokenRequestData]):
    """申请一次性认证令牌的请求。"""

    message_type: str = Field(default="AuthenticationTokenRequest", alias="messageType", description="向用户申请令牌授权。")


class AuthenticationTokenResponseData(VTSEmptyData):
    """认证令牌响应。"""

    authentication_token: str = Field(alias="authenticationToken", description="后续会话认证可复用的令牌。")


class AuthenticationTokenResponse(VTSResponseEnvelope[AuthenticationTokenResponseData]):
    """认证令牌响应信封。"""


class AuthenticationRequestData(VTSEmptyData):
    """使用令牌进行会话认证。"""

    plugin_name: str = Field(alias="pluginName", min_length=3, max_length=32, description="插件名称，必须与令牌申请时一致。")
    plugin_developer: str = Field(alias="pluginDeveloper", min_length=3, max_length=32, description="插件开发者名称，必须与令牌申请时一致。")
    authentication_token: str = Field(alias="authenticationToken", min_length=1, max_length=64, description="已获取到的认证令牌。")


class AuthenticationRequest(VTSRequestEnvelope[AuthenticationRequestData]):
    """会话认证请求。"""

    message_type: str = Field(default="AuthenticationRequest", alias="messageType", description="使用持久令牌认证当前连接。")


class AuthenticationResponseData(VTSEmptyData):
    """会话认证响应。"""

    authenticated: bool = Field(description="当前会话是否认证成功。")
    reason: str = Field(description="认证结果说明。")


class AuthenticationResponse(VTSResponseEnvelope[AuthenticationResponseData]):
    """会话认证响应信封。"""

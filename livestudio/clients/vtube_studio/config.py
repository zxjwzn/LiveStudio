"""VTube Studio client configuration models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VTubeStudioPluginInfo(BaseModel):
    """插件身份信息。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plugin_name: str = Field(
        min_length=3,
        max_length=32,
        description="插件名称。首次申请令牌与后续会话认证必须保持一致。",
    )
    plugin_developer: str = Field(
        min_length=3,
        max_length=32,
        description="插件开发者名称。首次申请令牌与后续会话认证必须保持一致。",
    )
    plugin_icon: str | None = Field(
        default=None,
        description="可选的 Base64 图标，需为 128x128 的 PNG 或 JPG。",
    )


class VTubeStudioConfig(BaseModel):
    """VTube Studio 连接配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(default="127.0.0.1", description="VTube Studio WebSocket 主机名。")
    port: int = Field(default=8001, ge=1, le=65535, description="VTube Studio WebSocket 端口。")
    api_name: str = Field(default="VTubeStudioPublicAPI", description="固定 API 名称。")
    api_version: str = Field(default="1.0", description="固定 API 版本。")
    connect_timeout: float = Field(default=10.0, gt=0, description="建立 WebSocket 连接超时秒数。")
    request_timeout: float = Field(default=10.0, gt=0, description="单次请求等待响应超时秒数。")
    user_agent: str = Field(default="LiveStudio/0.1.0", description="连接时附带的 User-Agent。")

    @property
    def websocket_url(self) -> str:
        """返回 WebSocket 地址。"""

        return f"ws://{self.host}:{self.port}"

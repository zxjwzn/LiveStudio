"""VTube Studio 客户端配置模型。"""

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

    plugin: VTubeStudioPluginInfo = Field(
        default_factory=lambda: VTubeStudioPluginInfo(
            plugin_name="LiveStudio",
            plugin_developer="Zaxpris",
        ),
        description="VTube Studio 插件身份信息。",
    )

    host: str = Field(default="127.0.0.1", description="VTube Studio WebSocket 主机名。")
    port: int = Field(default=8001, ge=1, le=65535, description="VTube Studio WebSocket 端口。")
    api_name: str = Field(default="VTubeStudioPublicAPI", description="固定 API 名称。")
    api_version: str = Field(default="1.0", description="固定 API 版本。")
    connect_timeout: float = Field(default=10.0, gt=0, description="建立 WebSocket 连接超时秒数。")
    request_timeout: float = Field(default=10.0, gt=0, description="单次请求等待响应超时秒数。")
    discovery_timeout: float = Field(default=5.0, gt=0, description="UDP discovery 等待超时秒数。")
    discovery_port: int = Field(default=47779, ge=1, le=65535, description="VTube Studio UDP 广播端口。")
    udp_buffer_size: int = Field(default=65536, ge=1024, le=1048576, description="UDP discovery 接收缓冲区大小。")
    event_queue_size: int = Field(default=128, ge=1, le=4096, description="每类事件队列缓存大小。")
    auto_resubscribe: bool = Field(default=True, description="重新认证成功后是否自动恢复事件订阅。")
    user_agent: str = Field(default="LiveStudio/0.1.0", description="连接时附带的 User-Agent。")

    @property
    def websocket_url(self) -> str:
        """返回 WebSocket 地址。"""

        return f"ws://{self.host}:{self.port}"

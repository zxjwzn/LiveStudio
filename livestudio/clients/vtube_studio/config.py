"""VTube Studio 客户端配置"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VTubeStudioPluginInfo(BaseModel):
    """插件身份信息"""

    model_config = ConfigDict(extra="forbid")

    plugin_name: str = Field(
        min_length=3,
        max_length=32,
        description="插件名称，第一次拿凭证和之后登录时都要保持一致",
    )
    plugin_developer: str = Field(
        min_length=3,
        max_length=32,
        description="插件作者名称，第一次拿凭证和之后登录时都要保持一致",
    )
    plugin_icon: str | None = Field(
        default=None,
        description="可选的 Base64 图标，需要是 128x128 的 PNG 或 JPG",
    )


class VTubeStudioConfig(BaseModel):
    """VTube Studio 连接设置"""

    model_config = ConfigDict(extra="forbid")

    plugin: VTubeStudioPluginInfo = Field(
        default_factory=lambda: VTubeStudioPluginInfo(
            plugin_name="LiveStudio",
            plugin_developer="Zaxpris",
        ),
        exclude=True,
        description="VTube Studio 插件身份信息",
    )

    ws_url: str = Field(
        default="ws://127.0.0.1:8001",
        description='VTube Studio 的 WebSocket 地址，像 "ws://127.0.0.1:8001" 这样写',
    )
    authentication_token: str | None = Field(
        default=None,
        description="保存下来的 VTube Studio 登录凭证",
    )
    api_name: str = Field(
        default="VTubeStudioPublicAPI",
        exclude=True,
        description="固定的接口名称",
    )
    api_version: str = Field(default="1.0", exclude=True, description="固定的接口版本")
    connect_timeout: float = Field(
        default=10.0,
        gt=0,
        description="连接 WebSocket 最多等多少秒",
    )
    request_timeout: float = Field(
        default=10.0,
        gt=0,
        description="单次请求等待响应超时秒数",
    )
    discovery_timeout: float = Field(
        default=5.0,
        gt=0,
        description="UDP 自动发现最多等多少秒",
    )
    discovery_port: int = Field(
        default=47779,
        ge=1,
        le=65535,
        description="VTube Studio 的 UDP 广播端口",
    )
    udp_buffer_size: int = Field(
        default=65536,
        ge=1024,
        le=1048576,
        exclude=True,
        description="UDP 自动发现接收数据时的缓冲大小",
    )
    event_queue_size: int = Field(
        default=128,
        ge=1,
        le=4096,
        exclude=True,
        description="每类事件队列缓存大小",
    )
    auto_resubscribe: bool = Field(
        default=True,
        description="重新认证成功后是否自动恢复事件订阅",
    )
    model_config_dir: str = Field(
        default="models/vtubestudio",
        exclude=True,
        description="按 VTube Studio 模型保存平台配置的文件夹",
    )
    user_agent: str = Field(
        default="LiveStudio/0.1.0",
        exclude=True,
        description="连接时带上的 User-Agent",
    )

    @field_validator("ws_url")
    @classmethod
    def validate_ws_url(cls, value: str) -> str:
        """检查 WebSocket 地址写得对不对"""

        if not value.startswith(("ws://", "wss://")):
            raise ValueError("ws_url 必须以 ws:// 或 wss:// 开头")
        return value

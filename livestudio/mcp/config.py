"""MCP 服务配置"""

from pydantic import BaseModel, ConfigDict, Field


class McpConfig(BaseModel):
    """MCP 服务的监听设置(host / port)。

    全为标量字段,内联默认(语义 A:自愈)。host 默认仅绑定本机回环,对外暴露需用户显式
    改为 0.0.0.0 等并自行承担访问控制风险(MCP 服务本身无鉴权)。
    """

    model_config = ConfigDict(extra="forbid")

    host: str = Field(
        default="127.0.0.1",
        min_length=1,
        description="MCP 服务监听主机；默认 127.0.0.1 仅本机可访问，改为 0.0.0.0 则对局域网开放",
    )
    port: int = Field(
        default=8420,
        ge=1,
        le=65535,
        description="MCP 服务监听端口",
    )

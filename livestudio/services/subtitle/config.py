"""字幕服务配置"""

from pydantic import BaseModel, ConfigDict, Field


class SubtitleConfig(BaseModel):
    """字幕 WebSocket 服务与 OBS 网页样式配置。

    host/port 控制独立小站监听;字体/颜色写入每次 ``begin`` 广播的样式字段。
    audio_delay_ms 补偿 TTS 呈现时钟相对合成时间戳的延迟(含 sink 缓冲垫)。
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "FONT"})

    enabled: bool = Field(default=True, description="启用字幕 WebSocket 服务")
    host: str = Field(
        default="127.0.0.1",
        min_length=1,
        description="字幕服务监听主机；默认 127.0.0.1 仅本机；0.0.0.0 对局域网开放（无鉴权）",
        json_schema_extra={"widget": "host", "hidden": True},
    )
    port: int = Field(
        default=8421, ge=1, le=65535, description="字幕服务监听端口", json_schema_extra={"widget": "port", "hidden": True}
    )
    font_path: str = Field(
        default="",
        description="自定义字体文件路径(.ttf/.otf)；留空使用网页默认 sans-serif",
        json_schema_extra={"widget": "file", "filter": "字体文件 (*.ttf *.otf);;所有文件 (*)"},
    )
    font_size: int = Field(default=48, ge=8, le=400, description="字幕字号(px)")
    font_color: str = Field(
        default="#FFFFFF",
        min_length=1,
        description="字幕字色(CSS 颜色,如 #FFFFFF)",
        json_schema_extra={"widget": "color"},
    )
    font_edge_color: str = Field(
        default="#000000",
        min_length=1,
        description="字幕描边色",
        json_schema_extra={"widget": "color"},
    )
    font_edge_width: float = Field(
        default=2.0,
        ge=0.0,
        le=32.0,
        description="字幕描边宽度(px)；0 表示无描边",
    )
    audio_delay_ms: int = Field(
        default=120,
        ge=0,
        le=5000,
        description="字幕相对音频时间戳的延迟(ms)，用于对齐喇叭出声",
    )
    clear_delay_ms: int = Field(
        default=2000,
        ge=0,
        le=30000,
        description="发声结束后清空字幕前的停留时间(ms)",
    )

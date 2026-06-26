"""GUI 自身的个性化配置模型

与业务配置(configs/ 下的音频、平台、模型配置)分离:这里只描述界面外观与
交互偏好,存于独立的 gui.yaml。所有字段都是可在设置页直接编辑的标量/枚举。
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ThemeMode(StrEnum):
    """界面主题模式"""

    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class UiLanguage(StrEnum):
    """界面语言"""

    ZH_CN = "zh_CN"
    EN = "en"


class GuiSettings(BaseModel):
    """GUI 个性化配置(界面外观与交互偏好)"""

    model_config = ConfigDict(extra="forbid")

    theme: ThemeMode = Field(
        default=ThemeMode.DARK,
        description="界面主题模式:浅色 / 深色 / 跟随系统",
    )
    accent_color: str = Field(
        default="#22C55E",
        description="Fluent 强调色(十六进制,如 #22C55E)",
    )
    font_point_size: int = Field(
        default=10,
        ge=8,
        le=24,
        description="界面正文字号(磅)",
    )
    language: UiLanguage = Field(
        default=UiLanguage.ZH_CN,
        description="界面语言",
    )
    log_level: str = Field(
        default="DEBUG",
        description="日志页 sink 接收级别",
    )
    restore_collapse_state: bool = Field(
        default=True,
        description="启动时恢复仪表盘平台栏的折叠状态",
    )
    collapsed_platforms: list[str] = Field(
        default_factory=list,
        description="记忆为折叠状态的平台名(restore_collapse_state 开启时生效)",
    )

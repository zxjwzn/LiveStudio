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


class GuiSettings(BaseModel):
    """GUI 个性化配置(界面外观与交互偏好)"""

    model_config = ConfigDict(extra="forbid")

    theme: ThemeMode = Field(
        default=ThemeMode.DARK,
        description="界面主题模式:浅色 / 深色 / 跟随系统",
    )
    accent_color: str = Field(
        default="#F56CCC",
        description="Fluent 强调色(十六进制,如 #22C55E)",
    )

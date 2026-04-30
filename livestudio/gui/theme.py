"""粉白色系调色板与主题常量。

基于粉色 (#FF6B9D) 和白色 (#FFFFFF) 派生出深浅变体，
构成完整的 UI 调色板。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class ColorToken:
    """单个颜色令牌，存储 hex 值。"""

    hex: str
    """#RRGGBB 或 #AARRGGBB 格式。"""

    def with_opacity(self, opacity: float) -> str:
        """返回带透明度的 hex 字符串 (#AARRGGBB)。

        Args:
            opacity: 0.0 ~ 1.0 之间的透明度值。
        """
        alpha = max(0, min(255, int(opacity * 255)))
        raw = self.hex.lstrip("#")
        # 如果已有 alpha 通道则替换，否则添加
        if len(raw) == 8:
            raw = raw[2:]  # 去掉原有 alpha
        return f"#{alpha:02X}{raw}"


# ─────────────────────────────────────────────────────────────
#  调色板 — 粉白色系
# ─────────────────────────────────────────────────────────────


class Colors:
    """粉白色系调色板。

    命名规则:
    - *_lightest / *_lighter / *_light  → 浅色变体
    - *_dark / *_darker / *_darkest     → 深色变体
    """

    # ── 主色 — 粉色 ──────────────────────────────────────────
    pink: Final = ColorToken("#FF6B9D")
    pink_lightest: Final = ColorToken("#FFF0F5")
    pink_lighter: Final = ColorToken("#FFD6E5")
    pink_light: Final = ColorToken("#FFA3C4")
    pink_dark: Final = ColorToken("#E8527F")
    pink_darker: Final = ColorToken("#CC3366")
    pink_darkest: Final = ColorToken("#992244")

    # ── 主色 — 白色 ──────────────────────────────────────────
    white: Final = ColorToken("#FFFFFF")
    white_dim: Final = ColorToken("#F8F0F4")
    white_muted: Final = ColorToken("#F0E4EB")
    white_soft: Final = ColorToken("#E8D8E0")

    # ── 背景色 ───────────────────────────────────────────────
    background: Final = ColorToken("#FFF5F9")
    """页面主背景 — 极浅粉白。"""

    surface: Final = ColorToken("#FFFFFF")
    """卡片/面板表面色。"""

    surface_variant: Final = ColorToken("#FFF0F5")
    """次级面板表面色 — 浅粉。"""

    surface_dim: Final = ColorToken("#F8E8F0")
    """更深的面板表面色。"""

    # ── 边框 & 分割线 ────────────────────────────────────────
    border: Final = ColorToken("#FFD6E5")
    """默认边框色 — 浅粉。"""

    border_subtle: Final = ColorToken("#F0E4EB")
    """更淡的边框色。"""

    border_accent: Final = ColorToken("#FF6B9D")
    """强调边框色 — 主粉色。"""

    divider: Final = ColorToken("#FFE8F0")
    """分割线颜色。"""

    # ── 文字 ─────────────────────────────────────────────────
    text_primary: Final = ColorToken("#3D2B33")
    """主文字色 — 深粉棕。"""

    text_secondary: Final = ColorToken("#8C6B7A")
    """次要文字色 — 中粉灰。"""

    text_hint: Final = ColorToken("#BFA3B0")
    """提示文字色 — 浅粉灰。"""

    text_on_accent: Final = ColorToken("#FFFFFF")
    """强调色上的文字 — 白色。"""

    # ── 强调 / 交互 ──────────────────────────────────────────
    accent: Final = ColorToken("#FF6B9D")
    """主强调色 — 粉色。"""

    accent_hover: Final = ColorToken("#FF85B1")
    """悬停态强调色 — 亮粉。"""

    accent_pressed: Final = ColorToken("#E8527F")
    """按下态强调色 — 深粉。"""

    accent_disabled: Final = ColorToken("#FFD6E5")
    """禁用态强调色 — 浅粉。"""

    # ── 状态色 ────────────────────────────────────────────────
    success: Final = ColorToken("#66D9A0")
    warning: Final = ColorToken("#FFB366")
    error: Final = ColorToken("#FF6B6B")
    info: Final = ColorToken("#66B3FF")

    # ── 阴影 ─────────────────────────────────────────────────
    shadow: Final = ColorToken("#FFD6E5")
    """卡片阴影色 — 浅粉。"""

    shadow_strong: Final = ColorToken("#E8A0BE")
    """更深的阴影色。"""

    # ── 控件专用 ──────────────────────────────────────────────
    slider_track: Final = ColorToken("#FFE0EC")
    """滑块轨道背景色。"""

    slider_track_active: Final = ColorToken("#FF6B9D")
    """滑块已填充轨道色。"""

    slider_thumb: Final = ColorToken("#FFFFFF")
    """滑块拇指色。"""

    toggle_track_off: Final = ColorToken("#E0D0D8")
    """开关关闭态轨道色。"""

    toggle_track_on: Final = ColorToken("#FF6B9D")
    """开关开启态轨道色。"""

    toggle_thumb: Final = ColorToken("#FFFFFF")
    """开关拇指色。"""

    checkbox_border: Final = ColorToken("#D4B8C4")
    """复选框边框色。"""

    checkbox_fill: Final = ColorToken("#FF6B9D")
    """复选框选中填充色。"""

    input_background: Final = ColorToken("#FFF8FB")
    """输入框背景色。"""

    input_border: Final = ColorToken("#E8D0DC")
    """输入框边框色。"""

    input_border_focus: Final = ColorToken("#FF6B9D")
    """输入框聚焦边框色。"""

    dropdown_background: Final = ColorToken("#FFFFFF")
    """下拉框背景色。"""

    dropdown_hover: Final = ColorToken("#FFF0F5")
    """下拉框选项悬停色。"""


# ─────────────────────────────────────────────────────────────
#  布局常量
# ─────────────────────────────────────────────────────────────


class Layout:
    """全局布局常量。"""

    # 圆角
    radius_sm: Final[int] = 6
    radius_md: Final[int] = 10
    radius_lg: Final[int] = 16
    radius_xl: Final[int] = 24

    # 间距
    spacing_xs: Final[int] = 4
    spacing_sm: Final[int] = 8
    spacing_md: Final[int] = 12
    spacing_lg: Final[int] = 16
    spacing_xl: Final[int] = 24

    # 内边距
    padding_sm: Final[int] = 8
    padding_md: Final[int] = 12
    padding_lg: Final[int] = 16
    padding_xl: Final[int] = 24

    # 动画时长 (毫秒)
    anim_fast: Final[int] = 150
    anim_normal: Final[int] = 250
    anim_slow: Final[int] = 400


class Typography:
    """字体常量。"""

    default_font_family: Final[str] = "Microsoft YaHei UI"
    """Windows 桌面端优先使用的中文 UI 字体。"""

    fallback_font_family: Final[str] = "Microsoft YaHei"
    """中文 UI 字体不可用时的回退字体。"""

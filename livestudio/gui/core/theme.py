"""粉白配色主题

集中定义色板 token 与 ft.Theme 构造。视图只引用语义 token（PALETTE.xxx），
禁止内联十六进制色值；换肤只需替换 Palette 实例。
"""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft

from .fonts import APP_FONT_FAMILY, ensure_app_font
from .view_models import ConnectionState, ControllerState


@dataclass(frozen=True)
class Palette:
    """粉白色板。所有色值集中于此。"""

    bg: str = "#FFF5F7"  # 应用主背景（极浅粉白）
    surface: str = "#FFFFFF"  # 卡片 / 面板表面
    surface_alt: str = "#FFEEF2"  # 次级表面 / 选中底色
    primary: str = "#F48FB1"  # 主品牌粉
    primary_hover: str = "#F06292"  # 主色悬停 / 按下
    primary_soft: str = "#FCE4EC"  # 主色浅染
    on_primary: str = "#FFFFFF"  # 主色之上的文字
    text: str = "#3E2C34"  # 主文本（暖褐）
    text_muted: str = "#9E8088"  # 次要文本 / 占位
    border: str = "#F8D7E0"  # 分割线 / 描边
    success: str = "#3FA796"  # 已连接 / 运行中
    warning: str = "#E8A33D"  # 连接中 / 重连中
    danger: str = "#E57373"  # 断开 / 错误
    accent_audio: str = "#CE93D8"  # 音频电平条渐变高位


PALETTE = Palette()


def build_theme(font_family: str | None = None) -> ft.Theme:
    """构造粉白 ft.Theme；font_family 为已注册的中文字体族名。"""

    return ft.Theme(
        font_family=font_family,
        color_scheme=ft.ColorScheme(
            primary=PALETTE.primary,
            on_primary=PALETTE.on_primary,
            surface=PALETTE.surface,
            on_surface=PALETTE.text,
            background=PALETTE.bg,
            on_background=PALETTE.text,
            error=PALETTE.danger,
        ),
        visual_density=ft.VisualDensity.COMFORTABLE,
        use_material3=True,
    )


def apply_page_theme(page: ft.Page) -> None:
    """把粉白主题应用到 page，并注册中文字体避免 CJK 字形回退。"""

    font_asset = ensure_app_font()
    if font_asset is not None:
        page.fonts = {APP_FONT_FAMILY: font_asset}
        family = APP_FONT_FAMILY
    else:
        # 兜底：无可用字体文件时退回系统字体族名（桌面端通常可解析）
        family = "Microsoft YaHei"

    page.theme = build_theme(family)
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = PALETTE.bg


def connection_color(state: ConnectionState) -> str:
    """连接状态 → 语义色。"""

    return {
        ConnectionState.CONNECTED: PALETTE.success,
        ConnectionState.CONNECTING: PALETTE.warning,
        ConnectionState.RECONNECTING: PALETTE.warning,
        ConnectionState.DISCONNECTED: PALETTE.text_muted,
        ConnectionState.ERROR: PALETTE.danger,
    }.get(state, PALETTE.text_muted)


def controller_color(state: ControllerState) -> str:
    """控制器状态 → 语义色。"""

    return {
        ControllerState.RUNNING: PALETTE.success,
        ControllerState.STOPPED: PALETTE.text_muted,
        ControllerState.ERROR: PALETTE.danger,
    }.get(state, PALETTE.text_muted)


def level_color(level: str) -> str:
    """日志级别 → 语义色。"""

    return {
        "TRACE": PALETTE.text_muted,
        "DEBUG": PALETTE.text_muted,
        "INFO": PALETTE.text,
        "SUCCESS": PALETTE.success,
        "WARNING": PALETTE.warning,
        "ERROR": PALETTE.danger,
        "CRITICAL": PALETTE.danger,
    }.get(level.upper(), PALETTE.text)

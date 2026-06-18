"""中文字体加载。

Flet 底层 Flutter 默认字体不含 CJK 字形，渲染中文时会回退到日文字体
（表现为"伪中文"/字形错乱）。这里注册一个简体中文字体并供主题设为默认。

策略：
- 字体文件放在 GUI assets 目录（fonts/ 子目录）下，按相对路径注册。
- 若 assets 中尚无字体，则从系统字体目录拷贝一个 TTF 进去（保持仓库干净，
  不提交大体积字体文件）。优先 TTF（Flutter 对 TTC 字体集支持不稳定）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

# 注册到 Flet 的字体族名（视图与主题统一引用）
APP_FONT_FAMILY = "LiveStudioCJK"

# GUI assets 目录与字体子目录
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
# 注册时使用的相对路径（相对 assets_dir）
APP_FONT_ASSET_PATH = "fonts/app-cjk.ttf"

# 候选系统中文字体（按优先级），仅取 TTF。Windows 常见路径。
_CANDIDATE_SYSTEM_FONTS: tuple[Path, ...] = (
    Path(r"C:\Windows\Fonts\Deng.ttf"),  # 等线，现代 UI 风格
    Path(r"C:\Windows\Fonts\simhei.ttf"),  # 黑体
    Path(r"C:\Windows\Fonts\simkai.ttf"),  # 楷体
    Path(r"C:\Windows\Fonts\simfang.ttf"),  # 仿宋
)


def ensure_app_font() -> str | None:
    """确保 assets 中存在可用中文字体，返回其相对注册路径；失败返回 None。

    - 已存在则直接返回。
    - 否则从候选系统字体拷贝第一个存在的进 assets/fonts/。
    """

    target = ASSETS_DIR / APP_FONT_ASSET_PATH
    if target.exists() and target.stat().st_size > 0:
        return APP_FONT_ASSET_PATH

    for source in _CANDIDATE_SYSTEM_FONTS:
        if source.exists():
            FONTS_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            return APP_FONT_ASSET_PATH

    return None

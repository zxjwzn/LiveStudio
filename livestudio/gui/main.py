"""GUI 入口。

装配 ServiceBridge（后端总线）+ AppShell（视图外壳）+ 粉白主题，
用 page.run_task 在 Flet 事件循环内启动现有后端服务，状态经桥接层
单向流入视图。

启动方式：
- 桌面窗口：  python -m livestudio.gui.main
- 浏览器预览：python -m livestudio.gui.main --web [--port 8550]
- 热重载开发：flet run livestudio/gui/main.py  （改代码自动刷新）
"""

from __future__ import annotations

import argparse

import flet as ft

from .bridge.service_bridge import ServiceBridge
from .core.fonts import ASSETS_DIR
from .core.theme import apply_page_theme
from .core.view_context import ViewContext
from .views.shell import AppShell

# page.fonts 的相对路径以此目录为根（必须传给 ft.app(assets_dir=...)）
_ASSETS_DIR = str(ASSETS_DIR)


async def main(page: ft.Page) -> None:
    """Flet 应用入口。"""

    page.title = "LiveStudio"
    page.padding = 0
    apply_page_theme(page)

    # ServiceBridge 持有 AppState 单一数据源与全部后端服务
    bridge = ServiceBridge(page)
    ctx = ViewContext(state=bridge.state, bridge=bridge)

    page.add(AppShell(ctx))

    # 在 Flet 事件循环内启动后端（不阻塞 UI；VTS 不可达时后台重连）
    page.run_task(bridge.start)

    async def _on_disconnect(_event: object) -> None:
        _ = _event
        await bridge.stop()

    page.on_disconnect = _on_disconnect


def run() -> None:
    """命令行入口：python -m livestudio.gui.main [--web] [--port N]。"""

    parser = argparse.ArgumentParser(description="LiveStudio GUI")
    parser.add_argument("--web", action="store_true", help="在浏览器中预览（默认开桌面窗口）")
    parser.add_argument("--port", type=int, default=0, help="--web 模式监听端口，0 为自动分配")
    args = parser.parse_args()

    if args.web:
        ft.app(target=main, view=ft.AppView.WEB_BROWSER, port=args.port, assets_dir=_ASSETS_DIR)
    else:
        ft.app(target=main, assets_dir=_ASSETS_DIR)


if __name__ == "__main__":
    run()

"""GUI 应用编排

持有后端服务(音频路由 / 动画管理器 / 各平台应用)与主窗口,把后端异步生命周期
绑定到窗口的打开与关闭。后端构造顺序镜像根 main.py,确保与 CLI 行为一致。

平台在 _build_platform_registrations() 工厂集中登记(后端 app + GUI 桥接成对):新增
平台只在该工厂多加一项,ServiceBridge 的 startup/shutdown 与各页渲染全自动覆盖。

七页均为真实页面:仪表盘/平台/音频/字幕/音频播放/日志/设置。
"""

import asyncio

from qfluentwidgets import InfoBar, InfoBarPosition

from livestudio.app import VTubeStudioApp
from livestudio.gui.bridge import McpBridge, PlatformRegistration, ServiceBridge, VTubeStudioPlatformBridge
from livestudio.gui.bridge.log_bridge import LogEntry
from livestudio.gui.bridge.subtitle_bridge import SubtitleBridge
from livestudio.gui.core import (
    GuiSettings,
    ThrottledNotifier,
    apply_all,
    create_gui_settings_manager,
    run_guarded,
)
from livestudio.gui.views.audio_view import AudioView
from livestudio.gui.views.dashboard_view import DashboardView
from livestudio.gui.views.logs_view import LogsView
from livestudio.gui.views.main_window import MainWindow
from livestudio.gui.views.mcp_view import McpView
from livestudio.gui.views.platform_view import PlatformView
from livestudio.gui.views.playback_view import PlaybackView
from livestudio.gui.views.settings_view import SettingsView
from livestudio.gui.views.subtitle_view import SubtitleView
from livestudio.mcp import LiveStudioMcpServer
from livestudio.services import AudioStreamRouter
from livestudio.services.animations import AnimationManager
from livestudio.services.subtitle import SubtitleService
from livestudio.utils.log import logger


def _build_platform_registrations(
    *,
    animation_manager: AnimationManager,
    audio_router: AudioStreamRouter,
) -> list[PlatformRegistration]:
    """构造平台后端及其 GUI 桥接登记。"""

    vtubestudio_app = VTubeStudioApp(
        animation_manager=animation_manager,
        audio_stream=audio_router,
    )
    return [
        PlatformRegistration(
            name="VTubeStudioApp",
            app=vtubestudio_app,
            bridge=VTubeStudioPlatformBridge(vtubestudio_app),
        ),
    ]


class GuiApplication:
    """GUI 顶层编排器:后端服务 + 主窗口 + 生命周期"""

    def __init__(self) -> None:
        self._settings_manager = create_gui_settings_manager()
        self.settings = GuiSettings()

        # 后端服务(构造顺序与 main.py 一致),此处不启动,生命周期由本类编排。
        # 各平台后端 app + GUI 桥接在工厂集中登记,新增平台只改工厂。
        self.audio_router = AudioStreamRouter()
        self.animation_manager = AnimationManager()
        self._platforms = _build_platform_registrations(
            animation_manager=self.animation_manager,
            audio_router=self.audio_router,
        )
        self._mcp_server = LiveStudioMcpServer()
        self._subtitle_service = SubtitleService(self.audio_router.subtitle_stream)
        self._service_bridge: ServiceBridge | None = None
        self._audio_view: AudioView | None = None
        self._playback_view: PlaybackView | None = None
        self._subtitle_view: SubtitleView | None = None
        # 日志告警通知:WARNING/ERROR 弹 InfoBar,按 (级别,消息) 去重节流避免刷屏
        self._notifier = ThrottledNotifier()

        self._window: MainWindow | None = None
        self._closing = False
        self._close_event = asyncio.Event()

    async def run(self) -> None:
        """加载设置、应用主题、构建并显示窗口,随后等待关闭信号"""

        self.settings = await self._settings_manager.load()
        apply_all(self.settings)

        bridge = ServiceBridge(
            audio_router=self.audio_router,
            platforms=self._platforms,
        )
        self._service_bridge = bridge

        # 先启动 MCP 服务,使 MCP 页构建时就能反映真实运行态与已加载的监听配置。
        await self._start_mcp_server()
        await self._start_subtitle_service()

        self._audio_view = AudioView(bridge.audio)
        self._playback_view = PlaybackView(bridge.audio)
        self._subtitle_bridge = SubtitleBridge(self._subtitle_service)
        self._subtitle_view = SubtitleView(self._subtitle_bridge)
        self._mcp_bridge = McpBridge(self._mcp_server)
        self._window = MainWindow(
            dashboard=DashboardView(bridge.audio, bridge.platforms),
            platform=PlatformView(bridge.platforms),
            audio=self._audio_view,
            subtitle=self._subtitle_view,
            playback=self._playback_view,
            logs=LogsView(bridge.logs),
            mcp=McpView(self._mcp_bridge),
            settings=SettingsView(self.settings, self._on_settings_changed),
        )
        self._window.set_close_request_handler(self._on_close_requested)
        self._window.show()

        # 窗口就绪后再接日志告警通知,确保 InfoBar 有持久 parent(主窗口)
        bridge.logs.logEmitted.connect(self._on_log_entry)

        await bridge.startup()
        await self._init_audio_view()
        await self._init_subtitle_view()
        await self._init_playback_view()
        await self._close_event.wait()

    async def _start_mcp_server(self) -> None:
        """启动 MCP 服务，失败时不阻断 GUI。"""

        try:
            await self._mcp_server.start()
        except Exception:
            logger.exception("MCP 服务启动失败，GUI 继续运行")

    async def _start_subtitle_service(self) -> None:
        """启动字幕服务(失败不阻断 GUI)。"""

        try:
            await self._subtitle_service.start()
        except Exception:
            logger.exception("字幕服务启动失败，已隔离(GUI 不受影响，OBS 字幕不可用)")

    async def _init_audio_view(self) -> None:
        """音频页按当前音源初始化切换条与对应配置编辑器"""

        if self._audio_view is None:
            return
        self._audio_view.load_config()

    async def _init_subtitle_view(self) -> None:
        """字幕页加载配置与端点展示"""

        if self._subtitle_view is None:
            return
        self._subtitle_view.load_config()

    async def _init_playback_view(self) -> None:
        """音频播放页加载当前配置并刷新输出设备下拉"""

        if self._playback_view is None:
            return
        self._playback_view.load_config()

    def _on_log_entry(self, entry: LogEntry) -> None:
        """把 WARNING/ERROR 级别日志弹成 InfoBar 通知(去重节流,避免同一告警刷屏)"""

        if entry.level not in ("WARNING", "ERROR"):
            return
        if self._window is None or not self._notifier.should_emit(entry.level, entry.message):
            return
        show = InfoBar.error if entry.level == "ERROR" else InfoBar.warning
        title = "错误" if entry.level == "ERROR" else "警告"
        show(
            title,
            entry.message,
            duration=4000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self._window,
        )

    def _on_settings_changed(self, settings: GuiSettings) -> None:
        """设置变更:持久化"""

        self.settings = settings
        run_guarded(self._persist_settings(settings), on_error=self._log_shutdown_error)

    async def _persist_settings(self, settings: GuiSettings) -> None:
        # 经持久管理器 save(config) 同步内存快照与文件(单源),无需一次性管理器--
        # 此前用 default_config 新建一次性管理器仅落盘,_settings_manager 内存快照滞后。
        await self._settings_manager.save(settings)

    def _on_close_requested(self) -> None:
        """窗口关闭请求:调度异步停机,完成后放行窗口关闭并结束 run()"""

        if self._closing:
            return
        self._closing = True
        run_guarded(self._shutdown_and_quit(), on_error=self._log_shutdown_error)

    async def _shutdown_and_quit(self) -> None:
        try:
            try:
                await self._subtitle_service.stop()
            except Exception as exc:
                if _is_exception_group(exc):
                    _log_exception_group("停止字幕服务失败，已隔离继续关闭", exc)
                else:
                    logger.exception("停止字幕服务失败，已隔离继续关闭")
            try:
                await self._mcp_server.stop()
            except Exception as exc:
                if _is_exception_group(exc):
                    _log_exception_group("停止 MCP 服务失败，已隔离继续关闭", exc)
                else:
                    logger.exception("停止 MCP 服务失败，已隔离继续关闭")
            if self._service_bridge is not None:
                try:
                    await self._service_bridge.shutdown()
                except Exception as exc:
                    if _is_exception_group(exc):
                        _log_exception_group("停止后端服务失败，已隔离继续关闭", exc)
                    else:
                        logger.exception("停止后端服务失败，已隔离继续关闭")
            if self._window is not None:
                self._window.confirm_close()
        finally:
            self._close_event.set()

    @staticmethod
    def _log_shutdown_error(exc: BaseException) -> None:
        logger.opt(exception=exc).error("GUI 停机流程异常: {}", exc)


def _is_exception_group(exc: BaseException) -> bool:
    return isinstance(getattr(exc, "exceptions", None), tuple)


def _log_exception_group(message: str, exc: BaseException) -> None:
    logger.error("{}: {}", message, exc)
    for index, sub_exc in enumerate(getattr(exc, "exceptions", ()), start=1):
        logger.opt(exception=sub_exc).error("{} 子异常 #{}: {}", message, index, sub_exc)

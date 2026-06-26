"""GUI 应用编排

持有后端三件套(音频路由 / 动画管理器 / VTS 应用)与主窗口,把后端异步生命周期
绑定到窗口的打开与关闭。后端构造顺序镜像根 main.py,确保与 CLI 行为一致。

仪表盘/平台页已移除,导航项保留但内容为空(EmptyView);音频/日志/设置为真实页面。
"""

import asyncio

from qfluentwidgets import InfoBar, InfoBarPosition

from livestudio.app import VTubeStudioApp
from livestudio.gui.bridge import ServiceBridge
from livestudio.gui.bridge.log_bridge import LogEntry
from livestudio.gui.core import (
    GuiSettings,
    ThrottledNotifier,
    apply_all,
    create_gui_settings_manager,
    create_gui_settings_manager_with,
    run_guarded,
)
from livestudio.gui.views.audio_view import AudioView
from livestudio.gui.views.empty_view import EmptyView
from livestudio.gui.views.logs_view import LogsView
from livestudio.gui.views.main_window import MainWindow
from livestudio.gui.views.settings_view import SettingsView
from livestudio.services import AudioStreamRouter
from livestudio.services.animations import AnimationManager
from livestudio.utils.log import logger


class GuiApplication:
    """GUI 顶层编排器:后端服务 + 主窗口 + 生命周期"""

    def __init__(self) -> None:
        self._settings_manager = create_gui_settings_manager()
        self.settings = GuiSettings()

        # 后端三件套(构造顺序与 main.py 一致),此处不启动,生命周期由本类编排。
        self.audio_router = AudioStreamRouter()
        self.animation_manager = AnimationManager()
        self.vtubestudio_app = VTubeStudioApp(
            animation_manager=self.animation_manager,
            audio_stream=self.audio_router,
        )
        self._service_bridge: ServiceBridge | None = None
        self._audio_view: AudioView | None = None
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
            vtubestudio_app=self.vtubestudio_app,
            log_level=self.settings.log_level,
        )
        self._service_bridge = bridge

        self._audio_view = AudioView(bridge.audio)
        self._window = MainWindow(
            dashboard=EmptyView("dashboardView"),
            platform=EmptyView("platformView"),
            audio=self._audio_view,
            logs=LogsView(bridge.logs),
            settings=SettingsView(self.settings, self._on_settings_changed),
        )
        self._window.set_close_request_handler(self._on_close_requested)
        self._window.show()

        # 窗口就绪后再接日志告警通知,确保 InfoBar 有持久 parent(主窗口)
        bridge.logs.logEmitted.connect(self._on_log_entry)

        await bridge.startup()
        await self._init_audio_view()
        await self._close_event.wait()

    async def _init_audio_view(self) -> None:
        """音频页按当前音源初始化切换条与对应配置编辑器"""

        if self._audio_view is None:
            return
        self._audio_view.load_config()

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
        """设置变更:持久化并把日志级别同步到 sink"""

        # 保留折叠记忆(设置页不涉及该字段,合并以免被覆盖)
        settings = settings.model_copy(update={"collapsed_platforms": self.settings.collapsed_platforms})
        self.settings = settings
        if self._service_bridge is not None:
            self._service_bridge.logs.set_level(settings.log_level)
        run_guarded(self._persist_settings(settings), on_error=self._log_shutdown_error)

    async def _persist_settings(self, settings: GuiSettings) -> None:
        # ConfigManager 无快照 setter,用 default_config 新建管理器直接落盘(模式 A)。
        manager = create_gui_settings_manager_with(settings)
        await manager.save()

    def _on_close_requested(self) -> None:
        """窗口关闭请求:调度异步停机,完成后放行窗口关闭并结束 run()"""

        if self._closing:
            return
        self._closing = True
        run_guarded(self._shutdown_and_quit(), on_error=self._log_shutdown_error)

    async def _shutdown_and_quit(self) -> None:
        if self._service_bridge is not None:
            await self._service_bridge.shutdown()
        if self._window is not None:
            self._window.confirm_close()
        self._close_event.set()

    @staticmethod
    def _log_shutdown_error(exc: BaseException) -> None:
        logger.error("GUI 停机流程异常: {}", exc)

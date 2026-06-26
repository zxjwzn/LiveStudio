"""VTube Studio 平台桥接

包装 VTubeStudioApp,把连接/断开/控制器启停/LAN 搜索/快速表情暴露为 GUI 可用的
同步方法 + Qt 信号。连接态用「可取消的 connect 任务」跟踪:任务进行中为 CONNECTING,
成功 CONNECTED,异常 ERROR,取消回 DISCONNECTED。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import QObject
from qfluentwidgets import FluentIcon

from livestudio.app import VTubeStudioApp
from livestudio.clients.vtube_studio.config import VTubeStudioConfig
from livestudio.clients.vtube_studio.errors import DiscoveryError
from livestudio.config import ConfigManager
from livestudio.gui.core import run_guarded
from livestudio.services.expression.models import NativeExpressionTrigger
from livestudio.services.platforms.model_config_service import PlatformModelConfigService
from livestudio.services.platforms.vtubestudio.config import VTubeStudioModelConfig
from livestudio.utils.log import logger
from livestudio.utils.paths import resolve_config_path

from .platform_bridge import ConnectionState, ModelConfigEntry, PlatformBridge

_PLATFORM_NAME = "vtubestudio"


class VTubeStudioPlatformBridge(PlatformBridge):
    """VTube Studio 的 GUI 桥接"""

    def __init__(self, app: VTubeStudioApp, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._connect_task: asyncio.Task[object] | None = None
        self._app.set_model_changed_listener(self._on_model_changed)

    @property
    def platform_name(self) -> str:
        return _PLATFORM_NAME

    @property
    def display_name(self) -> str:
        return "VTube Studio"

    @property
    def icon(self) -> FluentIcon:
        return FluentIcon.ROBOT

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"lan_discovery"})

    def connect_platform(self) -> None:
        """发起连接(可取消)。连接期间 start() 会无限重试,故状态停留 CONNECTING。"""

        if self._state in (ConnectionState.CONNECTING, ConnectionState.CONNECTED):
            return
        self._set_state(ConnectionState.CONNECTING)
        self._connect_task = run_guarded(self._connect(), on_error=self._on_connect_error)
        self._connect_task.add_done_callback(self._on_connect_done)

    async def _connect(self) -> None:
        await self._app.connect()

    def _on_connect_done(self, task: asyncio.Task[object]) -> None:
        self._connect_task = None
        if task.cancelled():
            self._set_state(ConnectionState.DISCONNECTED)
            return
        if task.exception() is not None:
            return  # 错误已由 on_error 处理并置 ERROR
        self._set_state(ConnectionState.CONNECTED)
        model = self._app.platform.current_model
        self.modelChanged.emit(model.model_id, model.model_name)

    def _on_connect_error(self, exc: BaseException) -> None:
        logger.error("VTube Studio 连接失败: {}", exc)
        self._set_state(ConnectionState.ERROR)
        self.errorOccurred.emit(str(exc))

    def disconnect_platform(self) -> None:
        """断开连接。若仍在连接中,先取消连接任务再停机。"""

        if self._connect_task is not None:
            self._connect_task.cancel()
            self._connect_task = None
        run_guarded(self._disconnect(), on_error=self._on_generic_error)

    async def _disconnect(self) -> None:
        await self._app.disconnect()
        self._set_state(ConnectionState.DISCONNECTED)
        self.controllersStateChanged.emit(False)

    def reconnect_platform(self) -> None:
        """重连:在同一任务里先断开再连接,避免断开未完成就发起连接导致竞态。"""

        if self._connect_task is not None:
            self._connect_task.cancel()
            self._connect_task = None
        self._set_state(ConnectionState.CONNECTING)
        self._connect_task = run_guarded(self._reconnect(), on_error=self._on_connect_error)
        self._connect_task.add_done_callback(self._on_connect_done)

    async def _reconnect(self) -> None:
        await self._app.disconnect()
        await self._app.connect()

    def start_controllers(self) -> None:
        """启动动画控制器"""

        run_guarded(self._start_controllers(), on_error=self._on_generic_error)

    async def _start_controllers(self) -> None:
        await self._app.start_controllers()
        self.controllersStateChanged.emit(True)

    def stop_controllers(self) -> None:
        """停止动画控制器"""

        run_guarded(self._stop_controllers(), on_error=self._on_generic_error)

    async def _stop_controllers(self) -> None:
        await self._app.stop_controllers()
        self.controllersStateChanged.emit(False)

    async def discover_addresses(self) -> list[str]:
        """LAN 搜索运行中的 VTS 实例,返回候选 ws 地址列表。

        LAN 发现用于「连接前」找地址,故不要求已连接;discovery 对象随服务构造即可用,
        无需先启动。无实例时后端按超时抛 DiscoveryError,这里收敛为空列表(对 UI 即
        「未发现」)。
        """

        config = self._app.platform.config
        try:
            broadcasts = await self._app.platform.listen_for_api(timeout=config.discovery_timeout)
        except DiscoveryError:
            return []
        addresses: list[str] = []
        for broadcast in broadcasts:
            host = broadcast.source_host
            if host:
                addresses.append(f"ws://{host}:{broadcast.data.port}")
        return addresses

    def trigger_expression(self, name: str) -> None:
        """快速触发一个原生表情(VTS .exp3.json)"""

        run_guarded(self._trigger_expression(name), on_error=self._on_generic_error)

    async def _trigger_expression(self, name: str) -> None:
        trigger = NativeExpressionTrigger(platform=_PLATFORM_NAME, native_ref=name)
        await self._app.platform.apply_native_expressions([trigger])

    def expression_names(self) -> list[str]:
        """当前模型可用的表情名(供快速触发按钮)。未加载模型时返回空。"""

        try:
            model_config = self._app.platform.model_config
        except RuntimeError:
            return []
        return [expression.name for expression in model_config.expressions]

    def _on_model_changed(self, model_id: str, model_name: str) -> None:
        self.modelChanged.emit(model_id, model_name)

    # --- 模型配置(平台页平铺编辑) ---

    def discover_model_configs(self) -> list[ModelConfigEntry]:
        """枚举该平台目录下所有模型配置 YAML(无 list API,按目录 glob)"""

        config_dir = resolve_config_path(self._app.platform.config.model_config_dir)
        if not config_dir.is_dir():
            return []
        return [ModelConfigEntry(display_name=path.stem, path=path) for path in sorted(config_dir.glob("*.yaml"))]

    def current_model_stem(self) -> str | None:
        """返回当前已加载模型对应的配置文件名(不含扩展名),供列表高亮当前模型。

        文件名规则为 {sanitize(name)}_{id[:5]},与 PlatformModelConfigService 一致;
        未连接/未加载模型时返回 None。
        """

        try:
            identity = self._app.platform.current_model
        except RuntimeError:
            return None
        safe_name = PlatformModelConfigService.sanitize_path_part(identity.model_name)
        safe_id = PlatformModelConfigService.sanitize_path_part(identity.model_id)[:5]
        return f"{safe_name}_{safe_id}"

    async def load_model_config(self, path: Path) -> VTubeStudioModelConfig:
        """加载单个模型配置文件"""

        manager: ConfigManager[VTubeStudioModelConfig] = ConfigManager(VTubeStudioModelConfig, path)
        return await manager.load()

    async def save_model_config(self, path: Path, config: VTubeStudioModelConfig) -> None:
        """保存模型配置(模式 A:以校验后的实例为默认值新建管理器直接落盘)"""

        manager: ConfigManager[VTubeStudioModelConfig] = ConfigManager(
            VTubeStudioModelConfig,
            path,
            default_config=config,
        )
        await manager.save()

    def ws_url(self) -> str:
        """当前连接地址"""

        return self._app.platform.config.ws_url

    async def apply_ws_url(self, ws_url: str) -> None:
        """校验并写入连接地址(具名属性赋值,非 setattr),持久化到磁盘。

        改动需重连才生效(start/restart 阶段才重读 config),由调用方决定何时重连。
        校验复用模型的 ws_url field_validator:先 model_validate 再赋值。
        """

        validated = self._app.platform.config.model_copy(update={"ws_url": ws_url})
        VTubeStudioConfig.model_validate(validated.model_dump())
        self._app.platform.config.ws_url = ws_url
        await self._app.platform.config_manager.save()

    def _on_generic_error(self, exc: BaseException) -> None:
        logger.error("VTube Studio 操作失败: {}", exc)
        self.errorOccurred.emit(str(exc))

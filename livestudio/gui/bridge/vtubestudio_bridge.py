"""VTube Studio 平台桥接

包装 VTubeStudioApp,把连接/断开/控制器启停/LAN 搜索/快速表情暴露为 GUI 可用的
同步方法 + Qt 信号。连接态用「可取消的 connect 任务」跟踪:任务进行中为 CONNECTING,
成功 CONNECTED,异常 ERROR,取消回 DISCONNECTED。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from pydantic import BaseModel
from PySide6.QtCore import QObject
from qfluentwidgets import FluentIcon

from livestudio.app import VTubeStudioApp
from livestudio.clients.vtube_studio.config import VTubeStudioConfig
from livestudio.clients.vtube_studio.errors import DiscoveryError
from livestudio.config import ConfigManager
from livestudio.gui.core import run_guarded
from livestudio.services.expression.models import EmotionKind, NativeExpressionTrigger
from livestudio.services.platforms.model_config_service import PlatformModelConfigService
from livestudio.services.platforms.vtubestudio.config import VTubeStudioModelConfig
from livestudio.utils.log import logger
from livestudio.utils.paths import resolve_config_path

from .platform_bridge import (
    ConnectionState,
    ControllerEntry,
    ControllerSpec,
    EmotionSpec,
    ModelConfigEntry,
    PlatformBridge,
)

_PLATFORM_NAME = "vtubestudio"

# 待机控制器静态规格(顺序即仪表盘展示顺序):内部名 / 中文展示名 / 行首图标。
# expression 为一次性控制器,无常驻运行态,不在此列(其触发能力归快速表情区)。
_CONTROLLER_SPECS: tuple[ControllerSpec, ...] = (
    ControllerSpec("blink", "眨眼", FluentIcon.VIEW),
    ControllerSpec("breathing", "呼吸", FluentIcon.HEART),
    ControllerSpec("gaze", "眼神注视", FluentIcon.VIEW),
    ControllerSpec("mouth_expression", "嘴部表情", FluentIcon.EMOJI_TAB_SYMBOLS),
    ControllerSpec("mouth_sync", "口型同步", FluentIcon.MICROPHONE),
)

# 情绪表情(AU 解算)静态规格:EmotionKind 值 / 中文名 / emoji。触发 expression 控制器
# 解算对应情绪(一次性:过渡→保持→自动回静息)。
_EMOTION_SPECS: tuple[EmotionSpec, ...] = (
    EmotionSpec(EmotionKind.JOY.value, "喜悦", "😊"),
    EmotionSpec(EmotionKind.ANGER.value, "愤怒", "😠"),
    EmotionSpec(EmotionKind.SADNESS.value, "悲伤", "😢"),
    EmotionSpec(EmotionKind.SURPRISE.value, "惊讶", "😲"),
    EmotionSpec(EmotionKind.SMUG.value, "阴险", "😏"),
    EmotionSpec(EmotionKind.WRY.value, "无奈", "😅"),
    EmotionSpec(EmotionKind.SHY.value, "害羞", "😳"),
)

_EXPRESSION_CONTROLLER = "expression"
_CAP_NATIVE_EXPRESSIONS = "native_expressions"
# 手动 toggle 的常驻原生表情独占一组作用域，与情绪解算(emotion)互不干扰。
_NATIVE_SCOPE = "manual"


class VTubeStudioPlatformBridge(PlatformBridge):
    """VTube Studio 的 GUI 桥接"""

    def __init__(self, app: VTubeStudioApp, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._connect_task: asyncio.Task[object] | None = None
        # GUI 侧镜像「当前已激活的原生表情名」:adapter 是集合替换式,toggle 时把整集
        # 传给 apply_native_expressions,由 adapter diff 增删。
        self._active_native: set[str] = set()
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
        return frozenset({"lan_discovery", _CAP_NATIVE_EXPRESSIONS})

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
        await self._cancel_all_controllers()
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
        await self._cancel_all_controllers()
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

    # --- 单控制器启停(仅运行态,不改模型配置) ---

    def controller_specs(self) -> list[ControllerSpec]:
        """待机控制器静态规格(与连接态无关),供仪表盘一次性建开关行"""

        return list(_CONTROLLER_SPECS)

    def controller_entries(self) -> list[ControllerEntry]:
        """当前可独立启停的待机控制器(blink/breathing/gaze/嘴部);未加载模型时为空。

        控制器实例在「连接并加载模型」后才由 _apply_model_config 建出,故未连接/未加载
        模型时 runtime.controllers 为空,这里返回空列表。
        """

        runtime = self._app.animation_manager.get_runtime(_PLATFORM_NAME)
        controllers = runtime.controllers
        entries: list[ControllerEntry] = []
        for spec in _CONTROLLER_SPECS:
            controller = controllers.get(spec.name)
            if controller is None:
                continue
            entries.append(
                ControllerEntry(name=spec.name, display_name=spec.display_name, running=controller.is_running)
            )
        return entries

    async def _cancel_all_controllers(self) -> None:
        """取消所有正在运行的待机控制器,并通知仪表盘开关复位。

        仪表盘开关用 runtime.start_controller(name) 单独起控制器,绕过了
        animation_manager.start(),故 manager/runtime 的 _started 仍为 False,
        断开/重连时 animation_manager.stop() 会因幂等守卫空转、残留控制器不停,
        其 run_cycle 继续向已断开的连接发参数而报错。这里直接逐个 cancel 控制器:
        cancel() 立即中断任务、不等当前周期跑完(stop() 会 await 自然结束,断开场景下
        那一等可能正好向已断连接发数据),并发单控制器信号让开关回到「已停止」。
        """

        runtime = self._app.animation_manager.get_runtime(_PLATFORM_NAME)
        for name, controller in runtime.controllers.items():
            if controller.is_running:
                await controller.cancel()
                self.controllerStateChanged.emit(name, False)
        self._reset_native_expressions()

    def _reset_native_expressions(self) -> None:
        """断开/重连时清空激活的原生表情镜像,并通知 UI 把 toggle 复位。

        连接断开后 adapter 状态失效,GUI 镜像也应清零;逐个发信号让 chip 回到未激活。
        """

        cleared = self._active_native
        self._active_native = set()
        for name in cleared:
            self.nativeExpressionStateChanged.emit(name, False)

    def start_controller(self, name: str) -> None:
        """启动单个待机控制器(仅运行态)"""

        run_guarded(self._start_controller(name), on_error=self._on_generic_error)

    async def _start_controller(self, name: str) -> None:
        runtime = self._app.animation_manager.get_runtime(_PLATFORM_NAME)
        started = await runtime.start_controller(name)
        # enabled=False 的控制器会被 start() 守卫跳过(started=False)。无论如何按真实
        # 运行态回报,让 UI 据此回弹开关并提示。
        controller = runtime.controllers.get(name)
        running = controller.is_running if controller is not None else False
        if not started and not running:
            self.errorOccurred.emit(f"控制器「{name}」在模型配置中已禁用,无法启动")
        self.controllerStateChanged.emit(name, running)

    def stop_controller(self, name: str) -> None:
        """停止单个待机控制器(仅运行态)"""

        run_guarded(self._stop_controller(name), on_error=self._on_generic_error)

    async def _stop_controller(self, name: str) -> None:
        runtime = self._app.animation_manager.get_runtime(_PLATFORM_NAME)
        await runtime.stop_controller(name)
        self.controllerStateChanged.emit(name, False)

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

    # --- 情绪表情(AU 解算,一次性) ---

    def emotion_specs(self) -> list[EmotionSpec]:
        """VTS 支持 AU 情绪解算,返回喜怒哀乐等情绪规格"""

        return list(_EMOTION_SPECS)

    def play_emotion(self, key: str) -> None:
        """触发一次情绪解算(execute expression 控制器);需已连接且控制器已建"""

        run_guarded(self._play_emotion(key), on_error=self._on_generic_error)

    async def _play_emotion(self, key: str) -> None:
        runtime = self._app.animation_manager.get_runtime(_PLATFORM_NAME)
        if _EXPRESSION_CONTROLLER not in runtime.controllers:
            self.errorOccurred.emit("表情控制器未就绪(请先连接并加载模型)")
            return
        await runtime.execute_controller(_EXPRESSION_CONTROLLER, emotion=key)

    # --- 原生表情(exp3,可激活/取消的 toggle) ---

    def native_expression_names(self) -> list[str]:
        """当前模型可 toggle 的 exp3 表情名。未加载模型时返回空。"""

        try:
            model_config = self._app.platform.model_config
        except RuntimeError:
            return []
        return [expression.name for expression in model_config.expressions]

    def active_native_expressions(self) -> set[str]:
        """当前已激活的 exp3 表情名集合"""

        return set(self._active_native)

    def toggle_native_expression(self, name: str) -> None:
        """切换某 exp3 表情的激活/取消;把更新后的整集传给 adapter(集合替换式)"""

        run_guarded(self._toggle_native_expression(name), on_error=self._on_generic_error)

    async def _toggle_native_expression(self, name: str) -> None:
        target = set(self._active_native)
        if name in target:
            target.discard(name)
        else:
            target.add(name)
        await self._apply_native(target)
        active = name in target
        self.nativeExpressionStateChanged.emit(name, active)

    def clear_native_expressions(self) -> None:
        """取消所有已激活的 exp3 表情"""

        run_guarded(self._clear_native_expressions(), on_error=self._on_generic_error)

    async def _clear_native_expressions(self) -> None:
        cleared = set(self._active_native)
        await self._apply_native(set())
        for name in cleared:
            self.nativeExpressionStateChanged.emit(name, False)

    async def _apply_native(self, target: set[str]) -> None:
        """把目标激活集合下发给 adapter(diff 增删),成功后更新 GUI 镜像"""

        triggers = [NativeExpressionTrigger(platform=_PLATFORM_NAME, native_ref=name) for name in target]
        await self._app.platform.apply_native_expressions(triggers, scope=_NATIVE_SCOPE)
        self._active_native = target

    def _on_model_changed(self, model_id: str, model_name: str) -> None:
        # 模型加载时后端 _sync_native_state 已按配置 active 激活了部分 exp3 表情,
        # 这里把 GUI 镜像同步成「配置里 active=True 的表情名」,使仪表盘 chip 反映真相。
        self._sync_active_from_config()
        self.modelChanged.emit(model_id, model_name)

    def _sync_active_from_config(self) -> None:
        """用当前模型配置里 active=True 的表情重建激活镜像,并发信号让 UI 同步。

        与后端 _sync_native_state 的真相对齐:它按 config.expressions[].active 激活
        到 VTS,故配置里 active 的即当前实际激活的。差异项发 nativeExpressionStateChanged。
        """

        try:
            model_config = self._app.platform.model_config
        except RuntimeError:
            new_active: set[str] = set()
        else:
            new_active = {expr.name for expr in model_config.expressions if expr.active}
        old_active = self._active_native
        self._active_native = new_active
        for name in old_active | new_active:
            now = name in new_active
            if (name in old_active) != now:
                self.nativeExpressionStateChanged.emit(name, now)

    # --- 模型配置(平台页平铺编辑) ---

    def discover_model_configs(self) -> list[ModelConfigEntry]:
        """枚举该平台目录下所有模型配置 YAML(无 list API,按目录 glob)。

        顺带读出每份配置的 model 身份(名/ID)供列表分开展示;文件损坏或缺字段时
        回退为仅用文件名 stem,不影响其它项。
        """

        config_dir = resolve_config_path(self._app.platform.config.model_config_dir)
        if not config_dir.is_dir():
            return []
        entries: list[ModelConfigEntry] = []
        for path in sorted(config_dir.glob("*.yaml")):
            model_name, model_id = self._read_identity(path)
            entries.append(
                ModelConfigEntry(display_name=path.stem, path=path, model_name=model_name, model_id=model_id)
            )
        return entries

    @staticmethod
    def _read_identity(path: Path) -> tuple[str, str]:
        """从模型配置 YAML 读出 (model_name, model_id);失败回退空串(列表改用 stem)"""

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return "", ""
        model = data.get("model") if isinstance(data, dict) else None
        if not isinstance(model, dict):
            return "", ""
        name = model.get("model_name")
        identifier = model.get("model_id")
        return (name if isinstance(name, str) else ""), (identifier if isinstance(identifier, str) else "")

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

    def model_config_type(self) -> type[BaseModel]:
        """VTS 模型配置类型,供通用配置组件渲染"""

        return VTubeStudioModelConfig

    async def load_model_config(self, path: Path) -> BaseModel:
        """加载单个模型配置文件"""

        manager: ConfigManager[VTubeStudioModelConfig] = ConfigManager(VTubeStudioModelConfig, path)
        return await manager.load()

    async def save_model_config(self, path: Path, config: BaseModel) -> None:
        """保存模型配置(模式 A:以校验后的实例为默认值新建管理器直接落盘)"""

        validated = VTubeStudioModelConfig.model_validate(config.model_dump())
        manager: ConfigManager[VTubeStudioModelConfig] = ConfigManager(
            VTubeStudioModelConfig,
            path,
            default_config=validated,
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

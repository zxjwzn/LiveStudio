"""VTube Studio 平台适配器。

包装现有 VTubeStudioApp / VTubeStudio / AnimationManager，把连接状态、模型、
动画控制器、表情等转换为 view-model 写入 AppState，并把 UI 意图转为后端调用。

要点：
- VTubeStudio.start() 在 VTS 不可达时会无限重连，因此 connect 必须放后台任务，
  适配器只反映 CONNECTING/CONNECTED/ERROR 状态，绝不阻塞桥接层启动。
- 所有状态写入经 async_bridge.post()，保证与事件循环 / UI 串行。
- app_factory 可注入，便于单元测试用假后端替换真实 VTubeStudioApp。
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
from typing import Any, Callable, Literal

from livestudio.utils.log import logger

from ...core.view_models import (
    ConnectionState,
    ControllerState,
    ControllerVM,
    DiscoveredEndpointVM,
    ExpressionVM,
    PlatformStatusVM,
)
from .base import PlatformAdapter, PlatformContext

# 后端控制器 key -> 中文展示名 / 类型
_CONTROLLER_LABELS: dict[str, tuple[str, Literal["idle", "oneshot"]]] = {
    "blink": ("眨眼", "idle"),
    "breathing": ("呼吸", "idle"),
    "body_swing": ("身体摇摆", "idle"),
    "mouth_expression": ("嘴型表情", "idle"),
    "mouth_sync": ("嘴型同步", "idle"),
    "expression": ("表情解算", "oneshot"),
}

# 情绪 key -> (中文名, emoji)
_EMOTION_LABELS: dict[str, tuple[str, str]] = {
    "joy": ("喜悦", "😊"),
    "sadness": ("悲伤", "😢"),
    "anger": ("愤怒", "😠"),
    "fear": ("恐惧", "😨"),
    "surprise": ("惊讶", "😲"),
    "disgust": ("厌恶", "😖"),
    "neutral": ("中性", "😐"),
}


def _default_app_factory(ctx: PlatformContext) -> Any:
    """默认后端应用工厂：构造真实 VTubeStudioApp。"""

    from livestudio.app import VTubeStudioApp

    return VTubeStudioApp(
        animation_manager=ctx.animation_manager,
        audio_stream=ctx.audio_router,
    )


class VTubeStudioAdapter(PlatformAdapter):
    """VTube Studio 平台适配器。"""

    platform_id = "vtube_studio"
    display_name = "VTube Studio"

    def __init__(
        self,
        ctx: PlatformContext,
        *,
        app_factory: Callable[[PlatformContext], Any] = _default_app_factory,
    ) -> None:
        super().__init__(ctx)
        self._app_factory = app_factory
        self._app: Any = None
        self._connect_task: asyncio.Task[None] | None = None
        self._status = PlatformStatusVM(
            platform_id=self.platform_id,
            display_name=self.display_name,
            connection=ConnectionState.DISCONNECTED,
        )

    # —— 生命周期 ——
    async def start(self) -> None:
        """构造并初始化后端应用，写入初始状态，随后后台自动连接。"""

        self._app = self._app_factory(self.ctx)
        await self._app.initialize()
        # 监听后端模型变更（首次加载 + 运行时换模型），据此自刷新模型名/控制器/表情。
        # 后端只广播「模型已就绪」信号，不知道 GUI 的存在——二者由此解耦。
        with contextlib.suppress(AttributeError):
            self._app.set_model_changed_listener(self._on_model_changed)
        endpoint = self._read_endpoint()
        self._set_status(connection=ConnectionState.DISCONNECTED, endpoint=endpoint)
        # 自动连接放后台，避免 VTS 不可达时阻塞
        self._connect_task = asyncio.create_task(self._connect_flow())

    async def _teardown(self) -> None:
        """取消连接任务、停止后端应用并复位状态（stop/disconnect 共用）。"""

        await self._cancel_connect_task()
        if self._app is not None:
            with contextlib.suppress(Exception):
                await self._app.stop()
        self._set_status(connection=ConnectionState.DISCONNECTED, model_name="", model_id="")
        self._publish_controllers([])
        self._publish_expressions([])

    async def stop(self) -> None:
        """取消连接任务并停止后端应用。"""

        await self._teardown()

    # —— 连接 ——
    async def connect(self, endpoint: str | None = None) -> None:
        """（重新）发起连接；endpoint 非空时写回配置。"""

        await self._cancel_connect_task()
        if endpoint:
            await self._write_endpoint(endpoint)
        self._connect_task = asyncio.create_task(self._connect_flow())

    async def disconnect(self) -> None:
        """断开连接并停止后端应用。"""

        await self._teardown()

    async def discover(self) -> list[DiscoveredEndpointVM]:
        """LAN 发现可用 VTube Studio 端点。"""

        if self._app is None:
            return []
        try:
            broadcast = await self._app.platform.discovery.discover_once()
        except Exception as exc:
            logger.warning("VTube Studio LAN 发现失败: {}", exc)
            return []
        data = broadcast.data
        result = [
            DiscoveredEndpointVM(
                name=data.window_title or "VTube Studio",
                host=broadcast.source_host or "127.0.0.1",
                port=data.port,
            )
        ]
        self.bridge.post(lambda: self.state.discovered.replace(result))
        return result

    # —— 状态 ——
    def status_vm(self) -> PlatformStatusVM:
        return self._status

    # —— 动画控制器代理 ——
    async def set_controller_enabled(self, key: str, enabled: bool) -> None:
        """启停指定控制器任务（不改模型配置的 enabled 持久值）。

        停止走 cancel()（立即取消当前周期），而非 stop()（会等当前动画跑完），
        以便暂停按钮即时生效、图标不延迟。
        """

        runtime = self._runtime()
        if runtime is None:
            return
        try:
            if enabled:
                await runtime.start_controller(key)
            else:
                await runtime.get_controller(key).cancel()
        except KeyError:
            logger.warning("未知动画控制器: {}", key)
            return
        self._refresh_controllers()

    # —— 表情 ——
    async def trigger_expression(self, key: str) -> None:
        """触发一次表情解算（一次性 expression 控制器）。"""

        runtime = self._runtime()
        if runtime is None:
            return
        try:
            await runtime.execute_controller("expression", emotion=key)
        except KeyError:
            logger.warning("表情控制器尚未就绪，无法触发: {}", key)

    # 模型配置读写继承基类的 P4 NotImplementedError 占位。

    # —— 内部 ——
    async def _connect_flow(self) -> None:
        """后台连接流程：CONNECTING → CONNECTED/ERROR，连接成功后刷新模型与控制器。"""

        self._set_status(connection=ConnectionState.CONNECTING, detail="正在连接…")
        try:
            await self._app.start()
        except asyncio.CancelledError:
            self._set_status(connection=ConnectionState.DISCONNECTED, detail="已取消连接")
            raise
        except Exception as exc:
            logger.warning("VTube Studio 连接失败: {}", exc)
            self._set_status(connection=ConnectionState.ERROR, detail=str(exc))
            return
        self._refresh_after_connect()

    def _refresh_after_connect(self) -> None:
        """连接成功后刷新连接状态、模型名、控制器与表情。"""

        model_name, model_id = self._current_model()
        self._set_status(
            connection=ConnectionState.CONNECTED,
            model_name=model_name,
            model_id=model_id,
            detail="",
        )
        self._refresh_controllers()
        self._refresh_expressions()

    def _on_model_changed(self, model_id: str, model_name: str) -> None:
        """后端模型变更回调（首次加载 + 运行时换模型）。

        后端在事件循环线程内同步调用本方法；只刷新模型名与动画/表情，不触碰
        连接状态（换模型时连接仍在）。状态写入经 _set_status/_publish_* 走
        async_bridge.post，线程安全。直接采用后端传入的身份，避免再查一次。
        """

        self._set_status(model_name=model_name, model_id=model_id)
        self._refresh_controllers()
        self._refresh_expressions()

    def _current_model(self) -> tuple[str, str]:
        """安全读取当前模型身份；未加载时返回空串。"""

        try:
            identity = self._app.platform.current_model
        except Exception:
            return "", ""
        return identity.model_name, identity.model_id

    def _runtime(self) -> Any:
        """取 VTS 平台动画运行时；未就绪返回 None。"""

        if self._app is None:
            return None
        try:
            return self.ctx.animation_manager.get_runtime(self._app.platform.name)
        except Exception:
            return None

    def _refresh_controllers(self) -> None:
        """把运行时控制器状态转为 ControllerVM 写入状态。"""

        runtime = self._runtime()
        if runtime is None:
            self._publish_controllers([])
            return
        vms: list[ControllerVM] = []
        for name, controller in runtime.controllers.items():
            label, ctype = _CONTROLLER_LABELS.get(name, (name, "idle"))
            state = ControllerState.RUNNING if controller.is_running else ControllerState.STOPPED
            vms.append(
                ControllerVM(
                    key=name,
                    display_name=label,
                    type=ctype,
                    state=state,
                    enabled=controller.enabled,
                )
            )
        self._publish_controllers(vms)

    def _refresh_expressions(self) -> None:
        """发布可快速触发的情绪表情列表。"""

        vms = [ExpressionVM(key=key, display_name=label, emoji=emoji) for key, (label, emoji) in _EMOTION_LABELS.items()]
        self._publish_expressions(vms)

    def _read_endpoint(self) -> str:
        """读取后端配置中的 WebSocket 地址。"""

        try:
            return self._app.platform.config.ws_url
        except Exception:
            return ""

    async def _write_endpoint(self, endpoint: str) -> None:
        """把新地址暂存到后端配置并显式落盘（下次连接生效）。

        走 ConfigManager.save() 持久化，而非裸 setattr——使 ws_url 与其它配置
        遵循同一「显式动作即落盘」时机；写入/保存失败记日志而非静默吞掉。
        """

        try:
            platform = self._app.platform
            platform.config.ws_url = endpoint
            await platform.config_manager.save()
        except Exception as exc:
            logger.warning("保存 VTube Studio 连接地址失败: {}", exc)

    async def _cancel_connect_task(self) -> None:
        task = self._connect_task
        self._connect_task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # —— 状态写入（统一经 async_bridge） ——
    def _set_status(
        self,
        *,
        connection: ConnectionState | None = None,
        endpoint: str | None = None,
        model_name: str | None = None,
        model_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        """更新 PlatformStatusVM 并发布到 AppState.platforms。

        每个字段传 None 表示「保持当前值」；传具体值（含空串）才覆盖。
        """

        current = self._status
        self._status = replace(
            current,
            connection=current.connection if connection is None else connection,
            endpoint=current.endpoint if endpoint is None else endpoint,
            model_name=current.model_name if model_name is None else model_name,
            model_id=current.model_id if model_id is None else model_id,
            detail=current.detail if detail is None else detail,
        )
        status = self._status
        self.bridge.post(lambda: self._publish_status(status))

    def _publish_status(self, status: PlatformStatusVM) -> None:
        """把单平台状态合并进 platforms 列表。"""

        platforms = list(self.state.platforms.value)
        for index, item in enumerate(platforms):
            if item.platform_id == status.platform_id:
                platforms[index] = status
                break
        else:
            platforms.append(status)
        self.state.platforms.replace(platforms)

    def _publish_controllers(self, vms: list[ControllerVM]) -> None:
        self.bridge.post(lambda: self.state.controllers.replace(vms))

    def _publish_expressions(self, vms: list[ExpressionVM]) -> None:
        self.bridge.post(lambda: self.state.expressions.replace(vms))

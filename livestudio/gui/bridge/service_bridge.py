"""ServiceBridge：桥接层总装配器。

持有 AppState、AsyncBridge、平台注册表、后端服务句柄、各控制器与平台适配器，
负责整体生命周期。视图通过 bridge.state 订阅状态，通过 bridge 的方法发意图。

装配方式（与现有 main.py 一致）：在 Flet async 入口内创建本对象，
page.run_task(bridge.start) 在同一事件循环启动后端，无需线程/进程隔离。
"""

from __future__ import annotations

import asyncio

import flet as ft

from livestudio.services.animations import AnimationManager
from livestudio.services.audio_stream import AudioStreamRouter
from livestudio.utils.log import logger

from ..core.app_state import AppState
from ..core.async_bridge import AsyncBridge
from ..core.registry import PlatformRegistry
from ..core.view_models import AudioSourceKind, PlatformDescriptor
from .audio_controller import AudioController
from .log_controller import LogController
from .platforms.base import PlatformAdapter, PlatformContext
from .platforms.vtube_studio import VTubeStudioAdapter


class ServiceBridge:
    """后端与状态之间的唯一通道与总装配器。"""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.state = AppState()
        self.async_bridge = AsyncBridge(page)
        self.registry = PlatformRegistry()

        # 后端服务（与现有 main.py 相同的装配）
        self.audio_router = AudioStreamRouter()
        self.animation_manager = AnimationManager()

        # 控制器
        self.audio = AudioController(self.state, self.audio_router)
        self.logs = LogController(self.state)

        # 平台适配器（按注册表实例化）
        self.adapters: dict[str, PlatformAdapter] = {}

        self._register_platforms()

    def _register_platforms(self) -> None:
        """注册内置平台。新增平台只需在此追加一行 register(...)。"""

        self.registry.register(
            PlatformDescriptor(
                id=VTubeStudioAdapter.platform_id,
                display_name=VTubeStudioAdapter.display_name,
                icon=ft.Icons.FACE_RETOUCHING_NATURAL,
                adapter_factory=VTubeStudioAdapter,
                panel_factory=None,  # P4 平台面板
            )
        )

    def _platform_context(self) -> PlatformContext:
        return PlatformContext(
            state=self.state,
            async_bridge=self.async_bridge,
            animation_manager=self.animation_manager,
            audio_router=self.audio_router,
        )

    async def start(self) -> None:
        """在事件循环内启动后端：日志 sink → 音频 → 各平台适配器。"""

        self.async_bridge.bind_loop(asyncio.get_running_loop())
        self.logs.start()
        await self.audio.start()

        ctx = self._platform_context()
        for desc in self.registry.all():
            adapter = desc.adapter_factory(ctx)
            self.adapters[desc.id] = adapter
            try:
                await adapter.start()
            except Exception:
                logger.exception("平台适配器启动失败: {}", desc.id)
        if self.adapters and not self.state.active_platform_id.value:
            self.state.active_platform_id.set(next(iter(self.adapters)))
        logger.info("ServiceBridge 已启动，平台 {} 个", len(self.adapters))

    async def stop(self) -> None:
        """停止全部平台适配器、音频与日志 sink。"""

        for adapter in self.adapters.values():
            try:
                await adapter.stop()
            except Exception:
                logger.exception("平台适配器停止失败: {}", adapter.platform_id)
        await self.audio.stop()
        await self.logs.stop()

    # —— 供视图调用的意图入口 ——
    def adapter(self, platform_id: str) -> PlatformAdapter | None:
        """按 id 取平台适配器。"""

        return self.adapters.get(platform_id)

    def active_adapter(self) -> PlatformAdapter | None:
        """取当前激活平台的适配器。"""

        return self.adapters.get(self.state.active_platform_id.value)

    async def switch_audio_source(self, kind: AudioSourceKind) -> None:
        """切换音频源（音频流页调用）。"""

        await self.audio.switch_source(kind)

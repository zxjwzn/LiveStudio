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
from ..core.choices_registry import ChoicesRegistry
from ..core.registry import PlatformRegistry
from ..core.view_models import AudioSourceKind, ConfigSectionVM, PlatformDescriptor
from .audio_controller import AudioController
from .log_controller import LogController
from .platforms.base import PlatformAdapter, PlatformContext
from .platforms.vtube_studio import VTubeStudioAdapter
from .schema_introspect import FieldOverride, introspect_model

# 动态下拉数据源 key（配置编辑器字段绑定用）。
# 注意：与麦克风配置模型里 device_name 的 gui_choices_source 保持一致。
CHOICES_AUDIO_INPUT_DEVICES = "audio.input_devices"

# 麦克风配置的 GUI 元数据（label/widget/hidden/choices_source）现已写在
# MicrophoneAudioStreamConfig 各字段的 json_schema_extra 里，introspect 直接读取，
# 无需在此重复声明。如需临时覆盖模型设定，可在此填 FieldOverride。
_MIC_FIELD_OVERRIDES: dict[str, FieldOverride] = {}


class ServiceBridge:
    """后端与状态之间的唯一通道与总装配器。"""

    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.state = AppState()
        self.async_bridge = AsyncBridge(page)
        self.registry = PlatformRegistry()
        self.choices = ChoicesRegistry()

        # 后端服务（与现有 main.py 相同的装配）
        self.audio_router = AudioStreamRouter()
        self.animation_manager = AnimationManager()

        # 控制器
        self.audio = AudioController(self.state, self.audio_router)
        self.logs = LogController(self.state)

        # 平台适配器（按注册表实例化）
        self.adapters: dict[str, PlatformAdapter] = {}

        self._register_platforms()
        self._register_choices()

    def _register_choices(self) -> None:
        """注册动态下拉数据源。新增数据源只需在此加一行 register(...)。"""

        self.choices.register(CHOICES_AUDIO_INPUT_DEVICES, self.audio.list_input_devices)

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
            try:
                await adapter.start()
            except Exception:
                # 启动失败的适配器不纳入 adapters：否则可能被选为 active_platform_id，
                # 导致 UI 默认激活一个不可用平台、后续意图调用全部静默失败。
                logger.exception("平台适配器启动失败，已跳过: {}", desc.id)
                continue
            self.adapters[desc.id] = adapter
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

    # —— 配置编辑（音频流页用，P4 模型配置同构复用）——
    def microphone_config_section(self) -> ConfigSectionVM:
        """把麦克风配置反射成 ConfigSectionVM（含字段级覆盖）。"""

        return introspect_model(
            self.audio.microphone_config(),
            section_id="microphone",
            title="麦克风",
            path_prefix="microphone",
            overrides=_MIC_FIELD_OVERRIDES,
        )

    def stage_microphone_field(self, path: str, value: object) -> None:
        """暂存麦克风配置单字段改动到内存（配置编辑器 on_change 调用，不落盘）。"""

        self.audio.stage_microphone_field(path, value)

    async def save_microphone_config(self) -> bool:
        """把暂存的麦克风配置落盘（保存按钮调用）。"""

        return await self.audio.save_microphone_config()

    async def restart_audio_source(self) -> bool:
        """以配置文件为准重启当前音频源（重启按钮调用）。"""

        return await self.audio.restart_source()

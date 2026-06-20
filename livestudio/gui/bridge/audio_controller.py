"""音频控制器：把音频流电平与音源状态桥接到 AppState。

AudioStreamRouter 是基于 asyncio.Queue 的发布订阅，消费发生在事件循环内，
因此电平更新无需跨线程 marshal，只需节流（默认 50ms）避免高频刷 UI。
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from livestudio.services.audio_stream import AudioSourceKind as BackendAudioSourceKind
from livestudio.services.audio_stream import AudioStreamRouter
from livestudio.utils.log import logger

from ..core.app_state import AppState
from ..core.view_models import AudioLevelVM, AudioSourceKind, ChoiceVM

# 节流间隔（秒）：电平更新最快每 50ms 写一次状态
_THROTTLE_SECONDS = 0.05


class AudioController:
    """订阅音频流，节流写入 state.audio_level；并代理音源切换。"""

    def __init__(self, state: AppState, audio_router: AudioStreamRouter) -> None:
        self.state = state
        self.router = audio_router
        self._subscription = None
        self._consume_task: asyncio.Task[None] | None = None
        self._last_emit: float = 0.0

    async def start(self) -> None:
        """启动音频路由器并开始消费电平。"""

        try:
            await self.router.start()
        except Exception as exc:
            logger.warning("音频流启动失败，仪表盘电平不可用: {}", exc)
            return
        self._subscription = self.router.subscribe(queue_maxsize=8)
        self._consume_task = asyncio.create_task(self._consume())
        self._publish_source(active=True)

    async def stop(self) -> None:
        """停止消费并释放订阅。"""

        task = self._consume_task
        self._consume_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if self._subscription is not None:
            with contextlib.suppress(Exception):
                self.router.unsubscribe(self._subscription)
            self._subscription = None
        self._publish_source(active=False)

    async def switch_source(self, kind: AudioSourceKind) -> None:
        """切换音频源；失败由路由器内部回滚，UI 只反映最终状态。"""

        backend_kind = BackendAudioSourceKind(kind.value)
        try:
            await self.router.switch_source(backend_kind)
        except Exception as exc:
            logger.warning("切换音频源失败: {}", exc)
            return
        self._publish_source(active=True)

    # —— 配置编辑支持 ——
    async def list_input_devices(self) -> list[ChoiceVM]:
        """枚举麦克风输入设备，供配置编辑器的动态下拉用（设备名作为值）。"""

        try:
            # 走路由器的设备枚举（与管线生命周期解耦）：即便活动源打不开导致
            # 管线被销毁，设备下拉仍能列出，用户得以换一个可用设备再重启。
            devices = await self.router.list_input_devices()
        except Exception as exc:
            logger.warning("枚举麦克风输入设备失败: {}", exc)
            return []
        return [ChoiceVM(value=device.name, label=device.name) for device in devices]

    def microphone_config(self) -> Any:
        """返回当前麦克风配置（Pydantic 模型），供 schema 反射。"""

        return self.router.config.microphone

    def stage_microphone_field(self, path: str, value: Any) -> None:
        """把配置编辑器的单字段改动暂存到内存配置模型（不落盘）。

        path 形如 "microphone.samplerate"，去掉前缀后即字段名。仅改内存，
        显式保存（save_microphone_config）才落盘，重启音源（restart_source）
        才让改动对运行中的流生效。
        """

        field_name = path.split(".")[-1]
        mic_config = self.router.config.microphone
        if not hasattr(mic_config, field_name):
            logger.warning("未知麦克风配置字段: {}", field_name)
            return
        try:
            setattr(mic_config, field_name, value)
        except Exception as exc:
            logger.warning("暂存麦克风配置 {} 失败: {}", field_name, exc)
            return
        # 改设备名时清掉旧的 device_index：后端解析优先按 index 匹配，残留的旧
        # index 会让新设备名失效（仍解析到旧设备）。清空后回退到按名称匹配。
        if field_name == "device_name":
            mic_config.device_index = None

    async def save_microphone_config(self) -> bool:
        """把内存中的麦克风配置落盘；返回是否成功。"""

        try:
            await self.router.config_manager.save()
        except Exception as exc:
            logger.warning("保存麦克风配置失败: {}", exc)
            return False
        logger.info("麦克风配置已保存")
        return True

    async def restart_source(self) -> bool:
        """就地软重启音频路由器，使（暂存到内存的）配置改动生效。

        关键：麦克风源持有的 config 与 router.config.microphone 是同一个活对象，
        暂存即就地改它，源已看到新配置。这里调路由器的 ``restart()``（软重启）——
        它委托活动源软重启：只回收/重建物理流，**不**清空订阅，因此路由器对外的
        下游订阅（如 MouthSyncController）与转发链路都得以保留，避免重启后无音频。
        语义上只有 ``stop()`` 才真正退出并断开对外契约。返回是否成功。
        """

        try:
            await self.router.restart()
        except Exception as exc:
            logger.warning("重启音频源失败: {}", exc)
            return False
        logger.info("音频源已重启（配置已生效）")
        return True

    async def _consume(self) -> None:
        """从订阅队列读取音频块，节流写入电平。"""

        subscription = self._subscription
        if subscription is None:
            return
        loop = asyncio.get_running_loop()
        try:
            while True:
                chunk = await subscription.queue.get()
                now = loop.time()
                if now - self._last_emit < _THROTTLE_SECONDS:
                    continue
                self._last_emit = now
                self.state.audio_level.set(
                    AudioLevelVM(
                        rms=float(chunk.analysis.rms),
                        peak=float(chunk.analysis.peak),
                        source=self._current_source(),
                        active=True,
                    )
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("音频电平消费任务异常")

    def _current_source(self) -> AudioSourceKind:
        """读取路由器当前活动源；未激活时回退麦克风。"""

        try:
            return AudioSourceKind(self.router.active_source_kind.value)
        except Exception:
            return AudioSourceKind.MICROPHONE

    def _publish_source(self, *, active: bool) -> None:
        """更新音源标识与激活态（保留最近电平值）。"""

        current = self.state.audio_level.value
        self.state.audio_level.set(
            AudioLevelVM(
                rms=current.rms if active else 0.0,
                peak=current.peak if active else 0.0,
                source=self._current_source(),
                active=active,
            )
        )
        self.state.audio_source.set(self._current_source())

"""音频控制器：把音频流电平与音源状态桥接到 AppState。

AudioStreamRouter 是基于 asyncio.Queue 的发布订阅，消费发生在事件循环内，
因此电平更新无需跨线程 marshal，只需节流（默认 50ms）避免高频刷 UI。
"""

from __future__ import annotations

import asyncio
import contextlib

from livestudio.services.audio_stream import AudioSourceKind as BackendAudioSourceKind
from livestudio.services.audio_stream import AudioStreamRouter
from livestudio.utils.log import logger

from ..core.app_state import AppState
from ..core.view_models import AudioLevelVM, AudioSourceKind

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

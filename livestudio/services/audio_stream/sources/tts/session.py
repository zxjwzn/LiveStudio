"""TTS 发声会话:领域生命周期,供调度器 await,不依赖 performance 包。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tts import TTSAudioStreamSource


class SpeakSession:
    """一次 speak 的呈现生命周期。

    - started: 呈现层首次把引擎产出的 PCM 帧推上总线(合成前的静音占位不算)
    - ended: 呈现任务结束(正常播完 / 打断 / 流卡死退出);不是 HTTP 断开
    """

    def __init__(self, source: TTSAudioStreamSource) -> None:
        self._source = source
        self._started = asyncio.Event()
        self._ended = asyncio.Event()

    @property
    def started(self) -> bool:
        return self._started.is_set()

    @property
    def ended(self) -> bool:
        return self._ended.is_set()

    def mark_started(self) -> None:
        self._started.set()

    def mark_ended(self, *, force: bool = False) -> None:
        """标记结束。

        默认仅在已 started 时生效,避免 stop 空转伪造起止;
        ``force=True`` 用于 cancel,确保 wait_* 解除阻塞。
        """

        if force:
            self._started.set()
            self._ended.set()
            return
        if not self._started.is_set():
            return
        self._ended.set()

    async def wait_started(self) -> None:
        await self._started.wait()

    async def wait_ended(self) -> None:
        await self._ended.wait()

    async def cancel(self) -> None:
        """打断本会话;若已非当前会话则仅 force 结束自身。"""

        if self._ended.is_set():
            return
        if self._source.current_session is self:
            await self._source.stop_speaking()
        # stop_speaking 在已 started 时会 mark_ended;未 started 时需 force 解锁
        if not self._ended.is_set():
            self.mark_ended(force=True)

"""TTS 音频流源

占位发声:``speak`` 生成正弦音按块实时发布(``source=TTS``),用于在真实 engine 接入前
打通"订阅 -> 总线接管 -> 本机播放 + 唇形"管道。真实 engine 接入后,把 ``_utterance``
里的合成替换为 engine 的 PCM async iterator(每块检查取消)即可,``speak``/``stop_speaking``
的取消-前置语义与发布机制保持不变。

空闲静音:源启动后、未发声期间持续发布响度 0 的静音块(``source=TTS``),让下游(唇形/电平/
本机播放)始终有时钟--唇形平滑回闭、电平持续刷新、本机播放输出流保持热开(发声起始无开流
延迟)。发声期间空闲循环**阻塞在事件上**(不轮询、不唤醒事件循环,避免给发声节流加抖动导致
本机播放欠载),由 ``_utterance`` 发布真实音频;发声结束置位事件自动恢复静音。
"""

from __future__ import annotations

import asyncio
import contextlib

import numpy as np

from ...base import AudioStreamSource
from ...models import AudioChunk, AudioSourceKind
from .config import TTSAudioStreamConfig


class TTSAudioStreamSource(AudioStreamSource):
    """TTS 音频流源(占位正弦音 engine)"""

    def __init__(self, config: TTSAudioStreamConfig) -> None:
        super().__init__()
        self.config = config
        self._utterance_task: asyncio.Task[None] | None = None
        self._idle_task: asyncio.Task[None] | None = None
        # 空闲事件:set=未发声(空闲循环发静音);clear=发声中(空闲循环阻塞,不轮询不唤醒事件循环,
        # 避免给发声的 asyncio.sleep 节流加抖动 -> 本机播放缓冲欠载)。
        self._idle_event = asyncio.Event()
        self._idle_event.set()

    async def _do_start(self) -> None:
        """启动 TTS 音频流资源:开启空闲静音循环,保持总线持续有块(响度 0)"""

        self._idle_task = asyncio.ensure_future(self._idle_loop())

    async def _do_stop(self) -> None:
        """停止 TTS 音频流资源(取消发声与空闲循环、释放订阅)"""

        self.stop_speaking()
        if self._utterance_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._utterance_task
            self._utterance_task = None
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
        self._idle_task = None
        self._idle_event.set()  # 复位为未发声,保证下次启动空闲循环能立即发静音
        self._clear_subscriptions()

    def speak(
        self,
        text: str,
        *,
        duration: float = 2.0,
        frequency: float = 440.0,
        **_opts: object,
    ) -> asyncio.Task[None]:
        """触发一次发声(取消进行中的旧发声后启动新的);返回发声任务。

        立即返回,发声在后台任务里按块实时发布。``text`` 暂未使用(占位正弦音);
        真实 engine 接入后由 engine 消费。
        """

        self.stop_speaking()
        self._idle_event.clear()  # 进入发声:阻塞空闲循环的静音发布
        self._utterance_task = asyncio.ensure_future(
            self._utterance(text, duration=duration, frequency=frequency),
        )
        return self._utterance_task

    def stop_speaking(self) -> None:
        """取消进行中的发声(若无则空操作)"""

        if self._utterance_task is not None and not self._utterance_task.done():
            self._utterance_task.cancel()

    @property
    def is_speaking(self) -> bool:
        """是否有发声任务进行中"""

        return self._utterance_task is not None and not self._utterance_task.done()

    async def _idle_loop(self) -> None:
        """空闲时持续发布响度 0 的静音块(source=TTS)。

        发声期间阻塞在 ``_idle_event`` 上(不轮询、不唤醒事件循环),由 ``_utterance``
        结束时置位恢复--这样空闲循环不给发声的 ``asyncio.sleep`` 节流加抖动,避免增加
        本机播放缓冲欠载概率。静音块速率与发声块一致(20ms/块)。
        """

        samplerate = self.config.samplerate
        channels = self.config.channels
        block_frames = max(1, int(samplerate * 0.02))
        delay = block_frames / samplerate
        while True:
            await self._idle_event.wait()  # 发声期间阻塞,不轮询
            self._publish_chunk(
                AudioChunk(
                    frames=block_frames,
                    samplerate=samplerate,
                    channels=channels,
                    data=np.zeros((block_frames, channels), dtype=np.float32),
                    source=AudioSourceKind.TTS,
                ),
            )
            await asyncio.sleep(delay)

    async def _utterance(
        self,
        _text: str,
        *,
        duration: float,
        frequency: float,
    ) -> None:
        """占位发声:生成 ``duration`` 秒正弦音,按 20ms 块实时发布(``source=TTS``)。

        实时节流(``asyncio.sleep``)模拟流式 engine 的产出速率,避免一次性灌满下游缓冲
        被丢最旧。TODO: 替换为真实 engine 的 PCM async iterator。
        """

        samplerate = self.config.samplerate
        channels = self.config.channels
        block_frames = max(1, int(samplerate * 0.02))
        total_frames = int(samplerate * duration)
        fade = min(block_frames, max(1, int(samplerate * 0.005)))  # 5ms 起止渐变,避免硬切爆破音
        me = asyncio.current_task()
        emitted = 0
        try:
            while emitted < total_frames:
                n = min(block_frames, total_frames - emitted)
                t = (np.arange(emitted, emitted + n, dtype=np.float64)) / samplerate
                wave = (0.3 * np.sin(2.0 * np.pi * frequency * t)).astype(np.float32)
                if emitted == 0:  # 起始淡入
                    wave[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
                if emitted + n >= total_frames:  # 结束淡出
                    tail = min(fade, n)
                    wave[-tail:] *= np.linspace(1.0, 0.0, tail, dtype=np.float32)
                data = wave.reshape(-1, 1)
                if channels > 1:
                    data = np.repeat(data, channels, axis=1)
                self._publish_chunk(
                    AudioChunk(
                        frames=n,
                        samplerate=samplerate,
                        channels=channels,
                        data=data,
                        source=AudioSourceKind.TTS,
                    ),
                )
                emitted += n
                await asyncio.sleep(n / samplerate)
        finally:
            # 仅当本次仍是当前发声任务时才解除空闲阻塞:被新 speak 取代的旧任务不置位
            if self._utterance_task is me:
                self._idle_event.set()

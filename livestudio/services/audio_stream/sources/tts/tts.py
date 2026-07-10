"""TTS 音频流源

驱动 TTS 引擎(基类 ``TtsEngine``)合成文本:引擎流式产出音频块(发到音频总线
``_publish_chunk``)与字幕段(发到 ``SubtitleStream``)。发声期间阻塞空闲静音循环
(``_idle_event``),避免给节流加抖动;取消-前置语义(新 speak 取消旧发声并 await 其清理,
保证字幕 finish 先于新 begin)。

路由器只转发当前激活源(无总线接管):要让 TTS 驱动唇形/音频播放,把激活源切到 TTS。
"""

from __future__ import annotations

import asyncio
import contextlib

import numpy as np

from livestudio.services.subtitle import SubtitleStream
from livestudio.utils.log import logger

from ...base import AudioStreamSource
from ...models import AudioChunk, AudioSourceKind
from .config import TTSAudioStreamConfig
from .engines import TtsAudioOutput, TtsSubtitleOutput, make_engine


class TTSAudioStreamSource(AudioStreamSource):
    """TTS 音频流源:驱动引擎合成,音频发总线、字幕发字幕流"""

    def __init__(self, config: TTSAudioStreamConfig, subtitle_stream: SubtitleStream) -> None:
        super().__init__()
        self.config = config
        self._subtitle_stream = subtitle_stream
        self._engine = make_engine(
            config.engine,
            sample_rate=config.samplerate,
            channels=config.channels,
        )
        self._idle_task: asyncio.Task[None] | None = None
        self._utterance_task: asyncio.Task[None] | None = None
        # set=未发声(空闲循环发静音);clear=发声中(空闲循环阻塞,不给节流加抖动)
        self._idle_event = asyncio.Event()
        self._idle_event.set()

    async def _do_start(self) -> None:
        """启动 TTS 音频流资源:开启空闲静音循环"""

        self._idle_task = asyncio.ensure_future(self._idle_loop())

    async def _do_stop(self) -> None:
        """停止 TTS 音频流资源(取消发声与空闲循环、释放订阅)"""

        await self.stop_speaking()
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
        self._idle_task = None
        self._clear_subscriptions()

    async def _do_restart(self) -> None:
        """软重启:取消发声 + 重启空闲循环,保留订阅者。

        与 stop 不同:不清空订阅--路由器对本源的转发订阅 ``_source_subscription``
        得以存活,重启(重载)后音频/字幕仍能流向下游。否则重载后 speak 发布的块到不了
        路由器(订阅被 _do_stop 清掉),表现为音频条/嘴型无反应。
        """

        await self.stop_speaking()
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
        self._idle_task = asyncio.ensure_future(self._idle_loop())

    async def _idle_loop(self) -> None:
        """空闲时持续发布响度 0 的静音块(source=TTS);发声期间阻塞在 ``_idle_event`` 上"""

        samplerate = self.config.samplerate
        channels = self.config.channels
        block_frames = max(1, int(samplerate * 0.02))
        delay = block_frames / samplerate
        while True:
            await self._idle_event.wait()
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

    async def speak(self, text: str, **opts: object) -> None:
        """触发一次发声(取消进行中的旧发声后启动新的);立即返回,发声在后台进行"""

        await self.stop_speaking()
        self._idle_event.clear()
        self._subtitle_stream.begin(text)
        self._utterance_task = asyncio.ensure_future(self._utterance(text, **opts))

    async def stop_speaking(self) -> None:
        """取消进行中的发声(若有);await 其清理(保证字幕 finish 先于后续 begin)"""

        task = self._utterance_task
        self._utterance_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @property
    def is_speaking(self) -> bool:
        """是否有发声任务进行中"""

        return self._utterance_task is not None and not self._utterance_task.done()

    async def _utterance(self, text: str, **opts: object) -> None:
        """迭代引擎合成:音频块发音频总线、字幕段发字幕流;结束(含取消)恢复空闲+发 finish"""

        try:
            async for output in self._engine.synthesize(text, **opts):
                if isinstance(output, TtsAudioOutput):
                    self._publish_chunk(
                        AudioChunk(
                            frames=output.frames,
                            samplerate=self._engine.sample_rate,
                            channels=self._engine.channels,
                            data=output.data,
                            source=AudioSourceKind.TTS,
                        ),
                    )
                elif isinstance(output, TtsSubtitleOutput):
                    self._subtitle_stream.publish_segments(output.segments)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("TTS 发声异常")
        finally:
            self._idle_event.set()
            self._subtitle_stream.finish()

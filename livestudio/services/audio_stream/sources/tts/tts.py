"""TTS 音频流源

驱动 TTS 引擎合成文本。**单一呈现时钟**:引擎突发 PCM 先入内部队列,由固定帧率
调度器按实时节奏切帧上音频总线;喇叭(AudioPlaybackSink)与嘴型/电平都消费同一总线,
因此唇音同源。

流程:
  speak → prepare 播放设备 → 取消旧发声 → 启动合成任务 + 调度任务
  合成: async for engine → 音频入 _audio_q, 字幕即时发 SubtitleStream
  调度: 每 1/60s 从 _audio_q 取满一帧(或静音补齐) → _publish_chunk
  stop/打断: 取消任务 → 清空 _audio_q → on_interrupt(flush 播放缓冲)

路由器只转发当前激活源:TTS 须为激活源才能驱动唇形/播放。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import numpy as np
from numpy.typing import NDArray

from livestudio.services.subtitle import SubtitleStream
from livestudio.utils.log import logger

from ...base import AudioStreamSource
from ...models import AudioChunk, AudioSourceKind
from .config import TTSAudioStreamConfig
from .engines import TtsAudioOutput, TtsSubtitleOutput, make_engine

# 与 MouthSyncController.update_interval / 麦克风 ~60fps 对齐
_FRAME_HZ = 60
_FRAME_SECONDS = 1.0 / _FRAME_HZ
# 内部合成队列上限(帧数≈秒);满则阻塞合成,形成反压,避免无界内存
_AUDIO_QUEUE_MAX_FRAMES = _FRAME_HZ * 120


class TTSAudioStreamSource(AudioStreamSource):
    """TTS 音频流源:引擎合成 + 固定帧率呈现调度"""

    def __init__(
        self,
        config: TTSAudioStreamConfig,
        subtitle_stream: SubtitleStream,
        *,
        on_interrupt: Callable[[], None] | None = None,
        on_prepare: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self._subtitle_stream = subtitle_stream
        self._on_interrupt = on_interrupt
        self._on_prepare = on_prepare
        self._engine = make_engine(
            config.engine,
            sample_rate=config.samplerate,
            channels=config.channels,
        )
        self._idle_task: asyncio.Task[None] | None = None
        self._synth_task: asyncio.Task[None] | None = None
        self._present_task: asyncio.Task[None] | None = None
        # set=空闲发静音; clear=发声中(呈现任务占用总线)
        self._idle_event = asyncio.Event()
        self._idle_event.set()
        # 合成 → 呈现:存放 float32 (frames, channels) 片段
        self._audio_q: asyncio.Queue[NDArray[np.float32]] = asyncio.Queue()
        self._queued_frames = 0
        self._queue_space = asyncio.Condition()

    def set_on_interrupt(self, on_interrupt: Callable[[], None] | None) -> None:
        self._on_interrupt = on_interrupt

    def set_on_prepare(self, on_prepare: Callable[[], Awaitable[None]] | None) -> None:
        self._on_prepare = on_prepare

    async def _do_start(self) -> None:
        self._idle_task = asyncio.ensure_future(self._idle_loop())

    async def _do_stop(self) -> None:
        await self.stop_speaking()
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
        self._idle_task = None
        self._clear_subscriptions()

    async def _do_restart(self) -> None:
        await self.stop_speaking()
        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._idle_task
        self._idle_task = asyncio.ensure_future(self._idle_loop())

    def _frame_params(self) -> tuple[int, int, int]:
        samplerate = self.config.samplerate
        channels = self.config.channels
        block_frames = max(1, int(round(samplerate * _FRAME_SECONDS)))
        return samplerate, channels, block_frames

    @staticmethod
    def _crossfade_edge(
        prev: NDArray[np.float32],
        nxt: NDArray[np.float32],
        *,
        fade_frames: int,
    ) -> NDArray[np.float32]:
        """在 nxt 帧头部与 prev 尾部短 crossfade,抹平有声/静音硬切。"""

        if fade_frames <= 0 or nxt.shape[0] == 0 or prev.shape[0] == 0:
            return nxt
        n = min(fade_frames, nxt.shape[0], prev.shape[0])
        if n <= 0:
            return nxt
        out = np.array(nxt, copy=True, dtype=np.float32)
        w = np.linspace(0.0, 1.0, n, dtype=np.float32).reshape(-1, 1)
        out[:n] = prev[-n:] * (1.0 - w) + out[:n] * w
        return out

    async def _idle_loop(self) -> None:
        samplerate, channels, block_frames = self._frame_params()
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
        """触发发声:先准备播放设备,再取消旧发声,启动合成+呈现。"""

        await self.stop_speaking()
        if self._on_prepare is not None:
            await self._on_prepare()
        self._idle_event.clear()
        self._subtitle_stream.begin(text)
        self._synth_task = asyncio.ensure_future(self._synthesize(text, **opts))
        self._present_task = asyncio.ensure_future(self._present())

    async def stop_speaking(self) -> None:
        """取消合成与呈现,清空内部队列,冲刷播放残留。"""

        tasks = [t for t in (self._synth_task, self._present_task) if t is not None]
        self._synth_task = None
        self._present_task = None
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            if not task.done():
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await self._clear_audio_queue()
        self._idle_event.set()
        if self._on_interrupt is not None:
            self._on_interrupt()

    @property
    def is_speaking(self) -> bool:
        synth = self._synth_task
        present = self._present_task
        return (synth is not None and not synth.done()) or (present is not None and not present.done())

    async def _clear_audio_queue(self) -> None:
        async with self._queue_space:
            while True:
                try:
                    self._audio_q.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._queued_frames = 0
            self._queue_space.notify_all()

    async def _enqueue_audio(self, data: NDArray[np.float32]) -> None:
        """入队 PCM(按帧切段);队列满时等待呈现消费形成反压。"""

        total = int(data.shape[0])
        if total <= 0:
            return
        # 按呈现帧长切段入队,避免单块超过队列上限导致永久阻塞
        _, _, block_frames = self._frame_params()
        offset = 0
        while offset < total:
            n = min(block_frames, total - offset)
            piece = np.ascontiguousarray(data[offset : offset + n])
            offset += n
            async with self._queue_space:
                while self._queued_frames + n > _AUDIO_QUEUE_MAX_FRAMES:
                    await self._queue_space.wait()
                await self._audio_q.put(piece)
                self._queued_frames += n

    async def _synthesize(self, text: str, **opts: object) -> None:
        """引擎迭代:音频入队,字幕即时发布。结束不发 finish(由 present 在耗尽后发)。"""

        try:
            async for output in self._engine.synthesize(text, **opts):
                if isinstance(output, TtsAudioOutput):
                    if output.frames <= 0:
                        continue
                    data = np.asarray(output.data, dtype=np.float32)
                    if data.ndim == 1:
                        data = data.reshape(-1, 1)
                    total = min(int(output.frames), int(data.shape[0]))
                    channels = max(1, self._engine.channels)
                    frame = np.ascontiguousarray(data[:total, :channels])
                    if frame.shape[1] < channels:
                        pad = np.zeros((total, channels - frame.shape[1]), dtype=np.float32)
                        frame = np.concatenate([frame, pad], axis=1)
                    await self._enqueue_audio(frame)
                elif isinstance(output, TtsSubtitleOutput):
                    self._subtitle_stream.publish_segments(output.segments)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("TTS 合成异常")
        # 合成结束:呈现任务会把队列耗尽后自行收尾

    async def _present(self) -> None:
        """固定帧率从队列取 PCM 上总线;队列空且合成已结束则 finish 并恢复空闲。

        SSE 间隙插静音、句尾零填充时与上一帧做短 crossfade,避免有声/0 硬切爆破音。
        """

        samplerate, channels, block_frames = self._frame_params()
        delay = block_frames / samplerate
        fade_frames = max(1, int(round(samplerate * 0.003)))
        carry = np.zeros((0, channels), dtype=np.float32)
        last = np.zeros((block_frames, channels), dtype=np.float32)
        try:
            while True:
                # 尽量凑满一帧
                while carry.shape[0] < block_frames:
                    synth_done = self._synth_task is None or self._synth_task.done()
                    if self._audio_q.empty() and synth_done:
                        break
                    try:
                        piece = await asyncio.wait_for(self._audio_q.get(), timeout=delay)
                    except TimeoutError:
                        break
                    async with self._queue_space:
                        self._queued_frames -= int(piece.shape[0])
                        if self._queued_frames < 0:
                            self._queued_frames = 0
                        self._queue_space.notify_all()
                    carry = np.concatenate([carry, piece], axis=0)

                synth_done = self._synth_task is None or self._synth_task.done()
                if carry.shape[0] == 0 and synth_done:
                    return

                if carry.shape[0] >= block_frames:
                    frame = np.ascontiguousarray(carry[:block_frames])
                    carry = carry[block_frames:]
                elif carry.shape[0] > 0 and synth_done:
                    pad = np.zeros((block_frames - carry.shape[0], channels), dtype=np.float32)
                    frame = np.ascontiguousarray(np.concatenate([carry, pad], axis=0))
                    carry = np.zeros((0, channels), dtype=np.float32)
                else:
                    # 合成仍在进行但本帧无足够音频(SSE 间隙):静音帧
                    frame = np.zeros((block_frames, channels), dtype=np.float32)

                prev_e = float(np.max(np.abs(last[-1]))) if last.size else 0.0
                next_e = float(np.max(np.abs(frame[0]))) if frame.size else 0.0
                if (prev_e > 1e-5) != (next_e > 1e-5):
                    frame = self._crossfade_edge(last, frame, fade_frames=fade_frames)
                last = frame

                self._publish_chunk(
                    AudioChunk(
                        frames=block_frames,
                        samplerate=samplerate,
                        channels=channels,
                        data=frame,
                        source=AudioSourceKind.TTS,
                    ),
                )
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise
        finally:
            self._idle_event.set()
            self._subtitle_stream.finish()
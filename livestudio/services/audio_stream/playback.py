"""音频播放订阅方:订阅音频总线,按源标识过滤后用 sounddevice 在本机输出设备播放

与电平表(AudioController)、唇形同步(MouthSyncController)同构--都是音频总线的下游
订阅者。区别在于本类把放行的音频块写进底层输出流让人听见。

线程模型(与麦克风源对称但反向):
- 麦克风:PortAudio 实时线程回调 -> call_soon_threadsafe -> 事件循环 _publish_chunk
- 本类:事件循环 drain 订阅队列 -> 转换 PCM -> 推线程安全缓冲 -> PortAudio OutputStream
  回调在实时线程取缓冲填充,欠载填零

时钟契约:
- 麦克风等实时源:块按采集时钟到达,本类短环缓冲丢最旧,懒开流。
- TTS:源侧按实时节奏上总线(与嘴型同源时钟);调用方在首包前 await prepare()
  打开输出流。首批真实音频前预填极短 jitter 静音(~1/60s)防欠载爆破音;
  欠载恢复时短 fade-in 抹平 0->有声接缝。

flush() 供打断丢弃未播残留。
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
from pydantic import BaseModel, ConfigDict, Field

from livestudio.services.lifecycle import AsyncServiceLifecycleMixin
from livestudio.utils.log import logger

from .base import AudioStreamSource
from .models import AudioChunk, AudioChunkSubscription, AudioSourceKind

# 环缓冲上限(秒):满则丢最旧。TTS 已按实时节奏上总线,只需吸收事件循环抖动。
_BUFFER_SECONDS = 0.5
# 无新放行块且缓冲耗尽超过此时长则关输出流(仅懒开流路径;prepare 会话内由调用方控制)
_IDLE_CLOSE_SECONDS = 0.5
# 订阅队列:须覆盖开流/转换尖峰,避免总线丢最旧
_SUBSCRIPTION_QUEUE_MAXSIZE = 256
# 首批真实音频前预填 jitter 静音(秒,约 1 帧):吸收调度抖动,远小于旧 100ms 垫
_JITTER_SECONDS = 1.0 / 60.0
# 欠载后恢复时的 fade-in 时长
_FADE_IN_SECONDS = 0.003


class OutputDeviceInfo(BaseModel):
    """输出设备信息"""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, description="设备索引")
    name: str = Field(min_length=1, description="设备名称")
    max_output_channels: int = Field(ge=0, description="最大输出声道数")
    default_samplerate: float = Field(gt=0, description="设备默认采样率")
    hostapi: int = Field(ge=0, description="所属 Host API 的编号")


class PlaybackConfig(BaseModel):
    """音频播放订阅方配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "VOLUME"})

    enabled: bool = Field(default=True, description="启用音频播放订阅方")
    output_device: int | None = Field(
        default=None,
        ge=0,
        description="输出设备索引;留空=系统默认输出(可设为虚拟声卡供 OBS 采集)",
        json_schema_extra={"icon": "SPEAKERS"},
    )
    samplerate: int | None = Field(
        default=None,
        gt=0,
        description="输出采样率;留空=使用设备默认(各源块会被重采样到此率)",
        json_schema_extra={"hidden": True},
    )
    channels: int = Field(
        default=1,
        ge=1,
        le=32,
        description="输出声道数",
        json_schema_extra={"hidden": True},
    )
    volume: float = Field(default=1.0, ge=0.0, le=4.0, description="音量增益(1.0=原音量)")
    sources: list[AudioSourceKind] = Field(
        default_factory=lambda: [AudioSourceKind.TTS],
        description="允许音频播放的音频源(默认仅 TTS;若加入麦克风需戴耳机以免啸叫)",
    )


class AudioPlaybackSink(AsyncServiceLifecycleMixin):
    """音频总线的音频播放订阅方:按源标识过滤后输出到本机设备"""

    def __init__(self, router: AudioStreamSource, config: PlaybackConfig) -> None:
        self._router = router
        self._config = config
        self._subscription: AudioChunkSubscription | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._buffer: deque[np.ndarray] = deque()
        self._buffer_lock = threading.Lock()
        self._buffer_frames = 0
        self._buffer_max_frames = int(48000 * _BUFFER_SECONDS)
        self._remainder: np.ndarray | None = None
        self._stream: sd.OutputStream | None = None
        self._samplerate: int | None = None
        self._channels = config.channels
        self._open_failed = False
        self._last_frame: np.ndarray = np.zeros(self._channels, dtype=np.float32)
        self._last_admit_monotonic: float = 0.0
        # prepare() 打开的会话:暂停空闲关流,直到缓冲耗尽后的自然结束或 flush/stop
        self._session_open = False
        # 会话内尚未为「首批真实音频」垫过 jitter
        self._need_jitter = False
        # 欠载后下一笔真实音频做短 fade-in(采样帧数;0=不需要)
        self._fade_in_remaining = 0

    async def prepare(self) -> None:
        """为即将开始的实时播放打开输出流并清空残留。

        TTS 在首包上总线之前调用:保证嘴型与喇叭共享同一呈现起点,无静音垫、无懒开流延迟。
        幂等;开流失败则后续块静默丢弃(已记日志)。
        """

        self.flush()
        if self._stream is None and not self._open_failed:
            await self._open_stream()
        self._session_open = self._stream is not None
        self._need_jitter = self._session_open
        self._fade_in_remaining = 0

    def flush(self) -> None:
        """丢弃未播 PCM 与订阅队列中的待处理块(打断/新 speak)。"""

        if self._subscription is not None:
            queue = self._subscription.queue
            while True:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        with self._buffer_lock:
            self._buffer.clear()
            self._buffer_frames = 0
        self._remainder = None
        self._last_frame = np.zeros(self._channels, dtype=np.float32)
        self._last_admit_monotonic = 0.0
        self._need_jitter = False
        self._fade_in_remaining = 0

    def _has_pending_audio(self) -> bool:
        with self._buffer_lock:
            if self._buffer_frames > 0:
                return True
        rem = self._remainder
        return rem is not None and rem.size > 0

    async def _do_start(self) -> None:
        """订阅总线并启动 drain(输出流默认懒开;TTS 由 prepare 显式打开)"""

        self._subscription = self._router.subscribe(queue_maxsize=_SUBSCRIPTION_QUEUE_MAXSIZE)
        self._drain_task = asyncio.create_task(self._drain())

    async def _do_stop(self) -> None:
        if self._drain_task is not None:
            self._drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drain_task
            self._drain_task = None

        stream = self._stream
        self._stream = None
        self._session_open = False
        if stream is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(stream.stop)
            with contextlib.suppress(Exception):
                await asyncio.to_thread(stream.close)

        if self._subscription is not None:
            self._router.unsubscribe(self._subscription)
            self._subscription = None

        with self._buffer_lock:
            self._buffer.clear()
            self._buffer_frames = 0
        self._remainder = None
        self._open_failed = False
        self._samplerate = None
        self._last_admit_monotonic = 0.0

    async def _drain(self) -> None:
        subscription = self._subscription
        if subscription is None:
            return
        while True:
            try:
                chunk = await asyncio.wait_for(
                    subscription.queue.get(),
                    timeout=_IDLE_CLOSE_SECONDS,
                )
            except TimeoutError:
                if self._has_pending_audio():
                    continue
                # prepare 会话在缓冲耗尽后结束,允许关流
                self._session_open = False
                await self._close_stream_idle()
                continue
            try:
                if chunk.source not in self._config.sources:
                    if (
                        self._stream is not None
                        and not self._session_open
                        and not self._has_pending_audio()
                        and self._admit_idle_too_long()
                    ):
                        await self._close_stream_idle()
                    continue
                if self._stream is None and not self._open_failed:
                    await self._open_stream()
                if self._stream is None:
                    continue
                self._last_admit_monotonic = time.monotonic()
                pcm = self._convert(chunk)
                if pcm.size > 0:
                    if self._need_jitter:
                        self._prefill_jitter()
                        self._need_jitter = False
                    self._push_buffer(pcm)
            except Exception:
                logger.exception("音频播放订阅处理音频块失败,已跳过该块")

    def _admit_idle_too_long(self) -> bool:
        return (
            self._last_admit_monotonic > 0.0
            and time.monotonic() - self._last_admit_monotonic > _IDLE_CLOSE_SECONDS
        )

    async def _close_stream_idle(self) -> None:
        if self._has_pending_audio() or self._session_open:
            return
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        with contextlib.suppress(Exception):
            await asyncio.to_thread(stream.stop)
        with contextlib.suppress(Exception):
            await asyncio.to_thread(stream.close)
        with self._buffer_lock:
            self._buffer.clear()
            self._buffer_frames = 0
        self._remainder = None
        self._last_frame = np.zeros(self._channels, dtype=np.float32)
        logger.debug("音频播放输出流空闲关闭")

    async def _open_stream(self) -> None:
        """打开 OutputStream;不预填静音(实时节奏源不需要垫,垫会制造唇音延迟)"""

        def _build() -> tuple[sd.OutputStream, int, int]:
            device_idx, default_sr = self._resolve_output_device()
            samplerate = self._config.samplerate or int(default_sr)
            stream = sd.OutputStream(
                device=device_idx,
                samplerate=samplerate,
                channels=self._channels,
                dtype="float32",
                blocksize=0,
                latency="low",
                callback=self._output_callback,
            )
            stream.start()
            return stream, samplerate, int(samplerate * _BUFFER_SECONDS)

        try:
            stream, samplerate, buffer_max = await asyncio.to_thread(_build)
        except Exception:
            logger.exception("打开音频输出流失败,音频播放将不可用")
            self._open_failed = True
            return
        self._stream = stream
        self._samplerate = samplerate
        self._buffer_max_frames = buffer_max
        self._last_admit_monotonic = time.monotonic()
        logger.info("音频播放输出流已开启: {}ch @ {}Hz", self._channels, samplerate)

    def _prefill_jitter(self) -> None:
        """预填极短静音,吸收事件循环抖动,避免空缓冲开跑立刻欠载爆破音。"""

        if self._samplerate is None:
            return
        frames = max(1, int(round(self._samplerate * _JITTER_SECONDS)))
        self._push_buffer(np.zeros(frames * self._channels, dtype=np.float32))

    def _apply_fade_in(self, pcm: np.ndarray) -> np.ndarray:
        """对欠载后恢复的真实音频做短 fade-in,抹平 0->有声硬接缝。"""

        if self._fade_in_remaining <= 0 or self._channels <= 0:
            return pcm
        samples = pcm.size
        if samples <= 0:
            return pcm
        frames = samples // self._channels
        if frames <= 0:
            return pcm
        n = min(self._fade_in_remaining, frames)
        ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
        shaped = pcm.reshape(frames, self._channels).copy()
        shaped[:n] *= ramp.reshape(-1, 1)
        self._fade_in_remaining -= n
        return np.ascontiguousarray(shaped.reshape(-1))

    def _resolve_output_device(self) -> tuple[int | None, float]:
        if self._config.output_device is not None:
            info = sd.query_devices(self._config.output_device)
            return self._config.output_device, float(info["default_samplerate"])
        default_output = sd.default.device[1]
        if default_output is None or default_output < 0:
            return None, 48000.0
        info = sd.query_devices(default_output)
        return int(default_output), float(info["default_samplerate"])

    def _convert(self, chunk: AudioChunk) -> np.ndarray:
        data = np.asarray(chunk.data)
        if data.dtype == np.float32:
            f = data.astype(np.float32)
        elif data.dtype == np.int16:
            f = data.astype(np.float32) * (1.0 / 32768.0)
        elif data.dtype == np.int32:
            f = data.astype(np.float32) * (1.0 / 2147483648.0)
        elif data.dtype == np.uint8:
            f = (data.astype(np.float32) - 128.0) * (1.0 / 128.0)
        else:
            f = data.astype(np.float32)

        if f.ndim == 1:
            f = f.reshape(-1, 1)
        frames, ch = f.shape

        sink_ch = self._channels
        if ch != sink_ch:
            if ch == 1 and sink_ch > 1:
                f = np.repeat(f, sink_ch, axis=1)
            elif ch > 1 and sink_ch == 1:
                f = f.mean(axis=1, keepdims=True)
            elif ch > sink_ch:
                f = f[:, :sink_ch]
            else:
                repeats = sink_ch // ch
                f = np.repeat(f, repeats, axis=1)[:, :sink_ch]

        f = np.asarray(f, dtype=np.float32)

        dst_sr = self._samplerate or chunk.samplerate
        if chunk.samplerate != dst_sr and frames > 0:
            new_frames = max(1, round(frames * dst_sr / chunk.samplerate))
            src_idx = np.arange(frames, dtype=np.float64)
            dst_idx = np.linspace(0.0, frames - 1, new_frames)
            resampled = np.empty((new_frames, sink_ch), dtype=np.float32)
            for channel in range(sink_ch):
                resampled[:, channel] = np.interp(dst_idx, src_idx, f[:, channel])
            f = resampled

        if abs(self._config.volume - 1.0) > 1e-9:
            f = f * self._config.volume

        return np.ascontiguousarray(f.reshape(-1))

    def _push_buffer(self, pcm: np.ndarray) -> None:
        if self._fade_in_remaining > 0 and pcm.size > 0 and float(np.max(np.abs(pcm))) > 1e-8:
            pcm = self._apply_fade_in(pcm)
        frames = pcm.size // self._channels
        if frames <= 0:
            return
        with self._buffer_lock:
            self._buffer.append(pcm)
            self._buffer_frames += frames
            while self._buffer_frames > self._buffer_max_frames and self._buffer:
                old = self._buffer.popleft()
                self._buffer_frames -= old.size // self._channels

    def _output_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info: object,
        status: object,
    ) -> None:
        _ = time_info, status
        try:
            out_pos = 0
            need = frames
            while need > 0:
                rem = self._remainder
                if rem is not None and rem.size > 0:
                    avail = rem.size // self._channels
                    take = min(need, avail)
                    outdata[out_pos : out_pos + take] = rem[: take * self._channels].reshape(
                        take, self._channels
                    )
                    out_pos += take
                    need -= take
                    self._remainder = rem[take * self._channels :] if take * self._channels < rem.size else None
                    continue
                with self._buffer_lock:
                    block = self._buffer.popleft() if self._buffer else None
                    if block is not None:
                        self._buffer_frames -= block.size // self._channels
                if block is None:
                    break
                self._remainder = block
            if out_pos > 0:
                self._last_frame = outdata[out_pos - 1].copy()
            if need > 0:
                # 欠载:淡出到零,并标记恢复后短 fade-in,避免 0->有声硬切爆破音
                fade = np.linspace(1.0, 0.0, need, dtype=np.float32).reshape(-1, 1)
                outdata[out_pos:] = self._last_frame * fade
                self._last_frame = np.zeros(self._channels, dtype=np.float32)
                if self._samplerate is not None:
                    self._fade_in_remaining = max(
                        self._fade_in_remaining,
                        max(1, int(round(self._samplerate * _FADE_IN_SECONDS))),
                    )
        except Exception:
            with contextlib.suppress(Exception):
                outdata[:] = 0.0

    @staticmethod
    def list_output_devices() -> list[OutputDeviceInfo]:
        result: list[OutputDeviceInfo] = []
        for index, raw in enumerate(sd.query_devices()):
            if not isinstance(raw, dict):
                continue
            name = raw.get("name")
            max_output = raw.get("max_output_channels")
            default_samplerate = raw.get("default_samplerate")
            hostapi = raw.get("hostapi")
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(max_output, int) or max_output <= 0:
                continue
            if isinstance(default_samplerate, bool) or not isinstance(default_samplerate, (int, float)):
                continue
            if not isinstance(hostapi, int):
                continue
            result.append(
                OutputDeviceInfo(
                    index=index,
                    name=name.strip(),
                    max_output_channels=max_output,
                    default_samplerate=float(default_samplerate),
                    hostapi=hostapi,
                ),
            )
        return result

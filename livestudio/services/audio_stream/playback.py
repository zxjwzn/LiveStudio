"""本机播放订阅方:订阅音频总线,按源标识过滤后用 sounddevice 在本机输出设备播放

与电平表(AudioController)、唇形同步(MouthSyncController)同构--都是音频总线的下游
订阅者。区别在于本类把放行的音频块写进底层输出流让人听见。

线程模型(与麦克风源对称但反向):
- 麦克风:PortAudio 实时线程回调 -> call_soon_threadsafe -> 事件循环 _publish_chunk
- 本类:事件循环 drain 订阅队列 -> 转换 PCM -> 推线程安全缓冲 -> PortAudio OutputStream
  回调在实时线程取缓冲填充,欠载填零

输出流懒开启:首个放行块到达才开 sd.OutputStream(不持设备空转);sink stop 时关闭。
跨活动源重启/切换存活--它是总线抽头,与具体源无关。
"""

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

# 缓冲上限(秒):超过则丢最旧,避免慢消费导致延迟堆积
_BUFFER_SECONDS = 0.5
# 空闲关流阈值(秒):TTS 静默超过此时长则关输出流,下次播放重开(重建缓冲垫,避免流常开
# 时缓冲从空开始、实时节流抖动导致连续欠载爆音)
_IDLE_CLOSE_SECONDS = 0.3
# 开流预填静音缓冲垫(秒):吸收 drain 实时节流抖动,防止欠载爆音(代价是对应时长的播放延迟)
_CUSHION_SECONDS = 0.1


class OutputDeviceInfo(BaseModel):
    """输出设备信息"""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, description="设备索引")
    name: str = Field(min_length=1, description="设备名称")
    max_output_channels: int = Field(ge=0, description="最大输出声道数")
    default_samplerate: float = Field(gt=0, description="设备默认采样率")
    hostapi: int = Field(ge=0, description="所属 Host API 的编号")


class PlaybackConfig(BaseModel):
    """本机播放订阅方配置"""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"icon": "VOLUME"})

    enabled: bool = Field(default=True, description="启用本机播放订阅方")
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
        description="允许本机播放的音频源(默认仅 TTS;若加入麦克风需戴耳机以免啸叫)",
    )


class AudioPlaybackSink(AsyncServiceLifecycleMixin):
    """音频总线的本机播放订阅方:按源标识过滤后输出到本机设备"""

    def __init__(self, router: AudioStreamSource, config: PlaybackConfig) -> None:
        self._router = router
        self._config = config
        self._subscription: AudioChunkSubscription | None = None
        self._drain_task: asyncio.Task[None] | None = None
        # 事件循环 drain -> 线程安全缓冲 -> PortAudio 实时线程回调
        self._buffer: deque[np.ndarray] = deque()
        self._buffer_lock = threading.Lock()
        self._buffer_frames = 0
        self._buffer_max_frames = int(48000 * _BUFFER_SECONDS)  # 流开启后按真实采样率重设
        self._remainder: np.ndarray | None = None  # 回调私有:当前未消费完的块(跨回调续接)
        self._stream: sd.OutputStream | None = None
        self._samplerate: int | None = None
        self._channels = config.channels
        self._open_failed = False
        self._last_frame: np.ndarray = np.zeros(self._channels, dtype=np.float32)  # 欠载淡出的起点
        self._last_tts_monotonic: float = 0.0  # 最近一次放行(TTS)块的时间,用于空闲关流判定

    async def _do_start(self) -> None:
        """订阅音频总线并启动 drain 任务(输出流懒开启)"""

        self._subscription = self._router.subscribe(queue_maxsize=64)
        self._drain_task = asyncio.create_task(self._drain())

    async def _do_stop(self) -> None:
        """停止 drain、关闭输出流、退订、清缓冲(唯一真正退出入口)"""

        if self._drain_task is not None:
            self._drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drain_task
            self._drain_task = None

        stream = self._stream
        self._stream = None
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
        self._last_tts_monotonic = 0.0

    async def _drain(self) -> None:
        """拉取订阅块,按源过滤后转换并推入缓冲;首个放行块懒开输出流。

        空闲(TTS 静默超阈值)时关流,下次播放重开并预填缓冲垫--避免输出流常开、缓冲从
        空开始时,drain 实时节流抖动导致连续欠载爆音。CancelledError 是 BaseException,
        不会被 except Exception 捕获,取消时自然向上传播终止任务。
        """

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
                await self._close_stream_idle()
                continue
            try:
                if chunk.source not in self._config.sources:
                    # 非放行源(如 mic):若 TTS 已静默超阈值,关流等下次播放重开重建缓冲垫
                    if self._stream is not None and self._tts_idle_too_long():
                        await self._close_stream_idle()
                    continue
                if self._stream is None and not self._open_failed:
                    await self._open_stream()
                if self._stream is None:
                    continue  # 开流失败:保持已启动但惰性空转,避免反复试错刷日志
                # 流常开重播(空闲关流未触发)时缓冲为空:补一次缓冲垫,避免无垫欠载爆音
                if self._buffer_frames == 0:
                    self._prefill_cushion()
                self._last_tts_monotonic = time.monotonic()
                pcm = self._convert(chunk)
                if pcm.size > 0:
                    self._push_buffer(pcm)
            except Exception:
                logger.exception("本机播放订阅处理音频块失败,已跳过该块")

    def _prefill_cushion(self) -> None:
        """预填一段静音缓冲垫,吸收节流抖动防欠载"""

        if self._samplerate is None:
            return
        cushion = np.zeros(int(self._samplerate * _CUSHION_SECONDS) * self._channels, dtype=np.float32)
        self._push_buffer(cushion)

    def _tts_idle_too_long(self) -> bool:
        """TTS 是否已静默超阈值(用于空闲关流判定)"""

        return (
            self._last_tts_monotonic > 0.0
            and time.monotonic() - self._last_tts_monotonic > _IDLE_CLOSE_SECONDS
        )

    async def _close_stream_idle(self) -> None:
        """空闲关流:停回调、关流、清缓冲,保留订阅等下次播放重开(重开时预填缓冲垫)"""

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
        logger.debug("本机播放输出流空闲关闭,下次播放将重开")

    async def _open_stream(self) -> None:
        """在独立线程里解析输出设备并打开 OutputStream;失败则标记惰性空转"""

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
            logger.exception("打开音频输出流失败,本机播放将不可用")
            self._open_failed = True
            return
        self._stream = stream
        self._samplerate = samplerate
        self._buffer_max_frames = buffer_max
        # 预填静音缓冲垫:吸收 drain 实时节流抖动,避免缓冲从空开始时连续欠载爆音
        cushion = np.zeros(int(samplerate * _CUSHION_SECONDS) * self._channels, dtype=np.float32)
        self._push_buffer(cushion)
        self._last_tts_monotonic = time.monotonic()
        logger.info("本机播放输出流已开启: {}ch @ {}Hz", self._channels, samplerate)

    def _resolve_output_device(self) -> tuple[int | None, float]:
        """返回 (设备索引, 默认采样率);索引 None 表示系统默认输出"""

        if self._config.output_device is not None:
            info = sd.query_devices(self._config.output_device)
            return self._config.output_device, float(info["default_samplerate"])
        default_output = sd.default.device[1]
        if default_output is None or default_output < 0:
            return None, 48000.0
        info = sd.query_devices(default_output)
        return int(default_output), float(info["default_samplerate"])

    def _convert(self, chunk: AudioChunk) -> np.ndarray:
        """把音频块归一为输出格式(float32, sink 声道, sink 采样率, 应用音量),返回扁平交织 1D"""

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
            else:  # 1 < ch < sink_ch
                repeats = sink_ch // ch
                f = np.repeat(f, repeats, axis=1)[:, :sink_ch]

        # 锚定为 float32,统一后续类型(整数/均值/复制等分支可能令推断类型过宽)
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
        """推入线程安全缓冲;超过上限丢最旧,避免延迟堆积"""

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
        """PortAudio 实时线程回调:从缓冲取数填充 outdata,欠载填零。绝不抛异常逸出"""

        _ = time_info, status
        try:
            out_pos = 0
            need = frames
            while need > 0:
                rem = self._remainder
                if rem is not None and rem.size > 0:
                    avail = rem.size // self._channels
                    take = min(need, avail)
                    outdata[out_pos : out_pos + take] = rem[: take * self._channels].reshape(take, self._channels)
                    out_pos += take
                    need -= take
                    self._remainder = rem[take * self._channels :] if take * self._channels < rem.size else None
                    continue
                with self._buffer_lock:
                    block = self._buffer.popleft() if self._buffer else None
                    if block is not None:
                        self._buffer_frames -= block.size // self._channels
                if block is None:
                    break  # 欠载:剩余填零
                self._remainder = block
            if out_pos > 0:
                self._last_frame = outdata[out_pos - 1].copy()
            if need > 0:
                # 欠载:从上一帧线性淡出到零,避免波形硬切产生爆破音
                fade = np.linspace(1.0, 0.0, need, dtype=np.float32).reshape(-1, 1)
                outdata[out_pos:] = self._last_frame * fade
                self._last_frame = np.zeros(self._channels, dtype=np.float32)
        except Exception:
            # 实时回调内任何异常都会被 PortAudio 吞掉或中断流,故整体兜底填零
            with contextlib.suppress(Exception):
                outdata[:] = 0.0

    @staticmethod
    def list_output_devices() -> list[OutputDeviceInfo]:
        """枚举系统输出设备(max_output_channels>0)"""

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

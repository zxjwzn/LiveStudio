"""用 sounddevice 获取实时麦克风声音"""

import asyncio
import contextlib
from collections.abc import Sequence
from typing import TypeGuard

import numpy as np
import sounddevice as sd

from livestudio.utils.log import logger

from ...base import AudioStreamSource
from ...models import AudioChunk, AudioChunkMetadata
from .config import MicrophoneAudioStreamConfig
from .models import InputDeviceInfo, RawInputDeviceInfo, SoundDeviceTimeInfo


class MicrophoneAudioStreamSource(AudioStreamSource):
    """提供指定麦克风的实时音频流采集能力"""

    def __init__(self, config: MicrophoneAudioStreamConfig) -> None:
        super().__init__()
        self.config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stream: sd.InputStream | None = None
        self._device_info: InputDeviceInfo | None = None
        # 实时回调里读的有效采样率快照，避免回调内访问可能抛错的属性
        self._samplerate: int | None = None

    @property
    def device_info(self) -> InputDeviceInfo:
        """返回当前选中的输入设备信息"""

        if self._device_info is None:
            raise RuntimeError("麦克风音频源尚未初始化")
        return self._device_info

    async def _do_initialize(self) -> None:
        """加载配置并解析目标输入设备"""

        self._loop = asyncio.get_running_loop()
        self._device_info = await self._resolve_input_device()
        self.config.device_name = self._device_info.name
        self.config.device_index = self._device_info.index
        logger.info(
            "麦克风音频源已初始化，目标设备: {} ({})",
            self.device_info.name,
            self.device_info.index,
        )

    async def _do_start(self) -> None:
        """启动麦克风输入流"""

        if self._loop is None or self._device_info is None:
            raise RuntimeError("麦克风音频源尚未初始化，请先调用 initialize()")

        await self._open_stream()
        logger.info("麦克风音频流已启动")

    async def _do_stop(self) -> None:
        """停止麦克风输入流并释放全部资源（含订阅）。"""

        try:
            await self._close_stream()
        finally:
            self._loop = None
            self._device_info = None
            self._clear_subscriptions()
            logger.info("麦克风音频流已停止")

    async def _do_restart(self) -> None:
        """就地软重启：按最新配置重选设备并重建输入流，保留订阅者。

        换设备等配置改动经此生效——关闭旧物理流、重新解析目标设备、开新流，
        但**不清空订阅**（路由器对本源的转发订阅得以存活，避免重启后下游无音频）。
        """

        await self._close_stream()
        self._loop = asyncio.get_running_loop()
        self._device_info = await self._resolve_input_device()
        self.config.device_name = self._device_info.name
        self.config.device_index = self._device_info.index
        await self._open_stream()
        logger.info(
            "麦克风音频源重启，目标设备: {} ({})",
            self.device_info.name,
            self.device_info.index,
        )

    async def _open_stream(self) -> None:
        """按当前设备/配置打开并启动底层输入流；指定设备打不开时回退默认设备。

        设备可能被占用或在解析后被拔出，导致 sd.InputStream 打开失败
        （如 PaErrorCode -9996）。此时不直接抛错让整条管线崩，而是回退到系统
        默认输入设备重试一次——这样配置指向的设备暂时不可用也能正常出声，
        并把实际启用的设备回写到 _device_info / config。仅当默认设备也打不开
        （或本就在用默认设备）时才抛出。
        """

        if self._device_info is None:
            raise RuntimeError("麦克风音频源尚未初始化，请先调用 initialize()")

        try:
            stream = await self._build_stream(self._device_info)
        except Exception as exc:
            logger.warning(
                "打开输入设备失败: {} ({})，尝试回退默认设备: {}",
                self._device_info.name,
                self._device_info.index,
                exc,
            )
        else:
            self._stream = stream
            return

        devices = await self.list_input_devices()
        fallback = await self._resolve_default_device(devices) if devices else None
        if fallback is None or fallback.index == self._device_info.index:
            raise RuntimeError(
                f"输入设备打开失败且无可用回退设备: {self._device_info.name}",
            )
        self._stream = await self._build_stream(fallback)
        self._device_info = fallback
        self.config.device_name = fallback.name
        self.config.device_index = fallback.index
        logger.info("已回退到默认输入设备: {} ({})", fallback.name, fallback.index)

    async def _build_stream(self, device: InputDeviceInfo) -> sd.InputStream:
        """按给定设备/当前配置打开并启动一条底层输入流。"""

        samplerate = self.config.samplerate or int(device.default_samplerate)
        stream = sd.InputStream(
            device=device.index,
            channels=self.config.channels,
            samplerate=samplerate,
            dtype=self.config.dtype,
            blocksize=self.config.blocksize,
            latency=self.config.latency,
            callback=self._handle_audio_callback,
        )
        try:
            await asyncio.to_thread(stream.start)
        except Exception:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(stream.close)
            raise
        # 流成功启动后再快照采样率，供实时回调直接读取
        self._samplerate = samplerate
        return stream

    async def _close_stream(self) -> None:
        """停止并关闭底层输入流（不动订阅、不回写配置）。

        刻意**不**把当前 device_info 回写 config：config 代表用户意图，
        关流属于运行态收尾，不应反向覆盖它——否则软重启时先关旧流会把旧设备
        写回 config，紧接着的 _resolve_input_device 又据此解析回旧设备，导致
        “换设备保存后重启仍是旧设备”。设备的权威回写只发生在
        _resolve_input_device 之后（_do_initialize / _do_restart 内）。
        """

        stream = self._stream
        self._stream = None
        self._samplerate = None
        if stream is not None:
            await asyncio.to_thread(stream.stop)
            await asyncio.to_thread(stream.close)

    async def list_input_devices(self) -> list[InputDeviceInfo]:
        """列出当前系统可用的输入设备"""

        devices = await asyncio.to_thread(sd.query_devices)
        return self._normalize_input_devices(devices)

    def _handle_audio_callback(
        self,
        indata: np.ndarray[
            tuple[int, int],
            np.dtype[np.float32] | np.dtype[np.int16] | np.dtype[np.int32] | np.dtype[np.uint8],
        ],
        frames: int,
        time_info: SoundDeviceTimeInfo,
        status: sd.CallbackFlags,
    ) -> None:
        # 该回调运行在 sounddevice/PortAudio 的实时线程：任何未捕获异常都会被
        # PortAudio 吞掉或中断音频流，故整体兜底。停流瞬间 _loop/_device_info 可能
        # 被并发清空，访问 self.device_info 或向已关闭的 loop 投递都可能抛 RuntimeError。
        try:
            loop = self._loop
            samplerate = self._samplerate
            if loop is None or samplerate is None:
                return

            chunk = AudioChunk(
                frames=frames,
                samplerate=samplerate,
                channels=self.config.channels,
                data=indata.copy(),
                overflowed=bool(status.input_overflow),
                metadata=AudioChunkMetadata(
                    input_buffer_adc_time=time_info.inputBufferAdcTime,
                    current_time=time_info.currentTime,
                    output_buffer_dac_time=time_info.outputBufferDacTime,
                    status=str(status),
                ),
            )
            loop.call_soon_threadsafe(self._push_chunk_nowait, chunk)
        except RuntimeError:
            # 典型为停流竞态：事件循环已关闭。静默丢弃当前块即可。
            return
        except Exception:
            # 构造/拷贝等非竞态异常：记录后丢弃本帧，避免逸出被 PortAudio 吞掉或中断流。
            logger.exception("麦克风音频回调异常，已忽略本帧")

    def _push_chunk_nowait(self, chunk: AudioChunk) -> None:
        # 运行在 loop 线程，不在回调 try 覆盖范围内，需自带兜底避免单块发布异常逸出事件循环。
        try:
            self._publish_chunk(chunk)
        except Exception:
            logger.exception("发布麦克风音频块失败，已跳过该块")

    async def _resolve_input_device(self) -> InputDeviceInfo:
        devices = await self.list_input_devices()
        if not devices:
            raise RuntimeError("未检测到可用的麦克风输入设备")

        selected_device = self._find_matching_device(
            devices,
            device_name=self.config.device_name,
            device_index=self.config.device_index,
        )
        if selected_device is not None:
            return selected_device

        return await self._resolve_default_device(devices)

    async def _resolve_default_device(
        self,
        devices: Sequence[InputDeviceInfo],
    ) -> InputDeviceInfo:
        """返回系统默认输入设备；无默认时回退到列表首个。"""

        default_input_index = await asyncio.to_thread(sd.default.device.__getitem__, 0)
        if default_input_index is not None and default_input_index >= 0:
            for device in devices:
                if device.index == int(default_input_index):
                    return device
        return devices[0]

    def _find_matching_device(
        self,
        devices: Sequence[InputDeviceInfo],
        *,
        device_name: str | None,
        device_index: int | None,
    ) -> InputDeviceInfo | None:
        if device_index is not None:
            return next(
                (device for device in devices if device.index == device_index),
                None,
            )

        if device_name is None:
            return None

        exact_match = next(
            (device for device in devices if device.name == device_name),
            None,
        )
        if exact_match is not None:
            return exact_match

        normalized_name = device_name.casefold()
        return next(
            (device for device in devices if normalized_name in device.name.casefold()),
            None,
        )

    def _normalize_input_devices(
        self,
        devices: Sequence[object],
    ) -> list[InputDeviceInfo]:
        normalized_devices: list[InputDeviceInfo] = []
        for index, raw_device in enumerate(devices):
            if not self._is_raw_input_device_info(raw_device):
                continue

            try:
                name = raw_device["name"].strip()
                if not name:
                    logger.warning("检测到名称为空的输入设备，已跳过: {}", raw_device)
                    continue

                max_input_channels = raw_device["max_input_channels"]
                if max_input_channels <= 0:
                    continue

                normalized_devices.append(
                    InputDeviceInfo(
                        index=index,
                        name=name,
                        max_input_channels=max_input_channels,
                        default_samplerate=float(raw_device["default_samplerate"]),
                        hostapi=raw_device["hostapi"],
                    ),
                )
            except ValueError:
                logger.exception("解析输入设备信息失败，已跳过: {}", raw_device)
                continue
        return normalized_devices

    def _is_raw_input_device_info(
        self,
        raw_device: object,
    ) -> TypeGuard[RawInputDeviceInfo]:
        if not isinstance(raw_device, dict):
            return False

        name = raw_device.get("name")
        max_input_channels = raw_device.get("max_input_channels")
        default_samplerate = raw_device.get("default_samplerate")
        hostapi = raw_device.get("hostapi")

        return (
            isinstance(name, str)
            and isinstance(max_input_channels, int)
            and not isinstance(default_samplerate, bool)
            and isinstance(default_samplerate, int | float)
            and isinstance(hostapi, int)
        )

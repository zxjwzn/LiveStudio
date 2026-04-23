"""基于 sounddevice 的实时麦克风输入服务。"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict, TypeGuard

import numpy as np
import sounddevice as sd

from livestudio.config import ConfigManager
from livestudio.log import logger

from .config import AudioInputConfig
from .models import AudioChunk, AudioChunkMetadata, InputDeviceInfo


class _SoundDeviceTimeInfo(Protocol):
    """sounddevice 回调时间信息协议。"""

    inputBufferAdcTime: float
    currentTime: float
    outputBufferDacTime: float


class _RawInputDeviceInfo(TypedDict):
    """sounddevice 输入设备原始信息。"""

    name: str
    max_input_channels: int
    default_samplerate: float | int
    hostapi: int
    index: NotRequired[int]


class AudioInputService:
    """提供指定麦克风的实时音频流采集能力。"""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        config_manager: ConfigManager[AudioInputConfig] | None = None,
    ) -> None:
        self.config_manager = config_manager or ConfigManager(
            AudioInputConfig,
            Path(config_path) if config_path is not None else Path("config") / "audio_input.yaml",
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[AudioChunk] | None = None
        self._stream: sd.InputStream | None = None
        self._started = False
        self._device_info: InputDeviceInfo | None = None
        self._dropped_chunks = 0

    @property
    def config(self) -> AudioInputConfig:
        """返回当前配置快照。"""

        return self.config_manager.config

    @property
    def device_info(self) -> InputDeviceInfo:
        """返回当前选中的输入设备信息。"""

        device_info = self._device_info
        if device_info is None:
            raise RuntimeError("音频输入服务尚未初始化")
        return device_info

    @property
    def dropped_chunks(self) -> int:
        """返回因队列已满被丢弃的音频块数量。"""

        return self._dropped_chunks

    async def initialize(self) -> None:
        """加载配置并解析目标输入设备。"""

        await self.config_manager.load()
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=self.config.queue_maxsize)
        self._device_info = await self._resolve_input_device()
        logger.info("音频输入服务已初始化，目标设备: {} ({})", self.device_info.name, self.device_info.index)

    async def start(self) -> None:
        """启动麦克风输入流。"""

        if self._started:
            return

        if self._loop is None or self._queue is None or self._device_info is None:
            raise RuntimeError("音频输入服务尚未初始化，请先调用 initialize()")

        stream = sd.InputStream(
            device=self._device_info.index,
            channels=self.config.channels,
            samplerate=self.config.samplerate or int(self._device_info.default_samplerate),
            dtype=self.config.dtype,
            blocksize=self.config.blocksize,
            latency=self.config.latency,
            callback=self._handle_audio_callback,
        )
        await asyncio.to_thread(stream.start)
        self._stream = stream
        self._started = True
        logger.info("音频输入流已启动")

    async def stop(self) -> None:
        """停止麦克风输入流。"""

        stream = self._stream
        self._stream = None
        if stream is None:
            self._started = False
            return

        await asyncio.to_thread(stream.stop)
        await asyncio.to_thread(stream.close)
        self._started = False
        logger.info("音频输入流已停止")

    async def close(self) -> None:
        """关闭服务并持久化配置。"""

        await self.stop()
        self._persist_selected_device_to_config()
        await self.config_manager.save()

    async def read_chunk(self, timeout: float | None = None) -> AudioChunk:
        """读取下一段音频数据。"""

        queue = self._require_queue()
        if timeout is None:
            return await queue.get()
        return await asyncio.wait_for(queue.get(), timeout=timeout)

    async def list_input_devices(self) -> list[InputDeviceInfo]:
        """列出当前系统可用的输入设备。"""

        devices = await asyncio.to_thread(sd.query_devices)
        return self._normalize_input_devices(devices)

    async def get_microphone_devices(self) -> list[InputDeviceInfo]:
        """返回当前所有可用麦克风设备。"""

        return await self.list_input_devices()

    async def select_input_device(
        self,
        *,
        device_name: str | None = None,
        device_index: int | None = None,
    ) -> InputDeviceInfo:
        """根据设备名称或索引选择麦克风设备。"""

        has_device_name = device_name is not None
        has_device_index = device_index is not None
        if has_device_name == has_device_index:
            raise ValueError("必须且只能提供 device_name 或 device_index 其中之一")

        devices = await self.list_input_devices()
        selected_device = self._find_matching_device(
            devices,
            device_name=device_name,
            device_index=device_index,
        )
        if selected_device is None:
            selector = device_name if device_name is not None else device_index
            raise RuntimeError(f"指定的麦克风设备不存在或不可用: {selector}")

        self._apply_selected_device(selected_device)
        was_started = self._started
        if was_started:
            await self.stop()
            await self.start()

        logger.info("音频输入设备已切换为: {} ({})", selected_device.name, selected_device.index)
        return selected_device

    async def reload_device(self) -> None:
        """根据最新配置重新选择设备并重启输入流。"""

        await self.config_manager.load()
        was_started = self._started
        if was_started:
            await self.stop()

        self._queue = asyncio.Queue(maxsize=self.config.queue_maxsize)
        self._device_info = await self._resolve_input_device()
        logger.info("音频输入设备已刷新为: {} ({})", self.device_info.name, self.device_info.index)

        if was_started:
            await self.start()

    def _persist_selected_device_to_config(self) -> None:
        """将当前已选设备写回配置快照。"""

        device_info = self._device_info
        if device_info is None:
            return

        self.config.device_name = device_info.name
        self.config.device_index = device_info.index

    def _handle_audio_callback(
        self,
        indata: np.ndarray[tuple[int, int], np.dtype[np.float32] | np.dtype[np.int16] | np.dtype[np.int32] | np.dtype[np.uint8]],
        frames: int,
        time_info: _SoundDeviceTimeInfo,
        status: sd.CallbackFlags,
    ) -> None:
        loop = self._loop
        queue = self._queue
        if loop is None or queue is None:
            return

        chunk = AudioChunk(
            frames=frames,
            samplerate=self.config.samplerate or int(self.device_info.default_samplerate),
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

    def _push_chunk_nowait(self, chunk: AudioChunk) -> None:
        queue = self._queue
        if queue is None:
            return

        try:
            queue.put_nowait(chunk)
        except asyncio.QueueFull:
            self._dropped_chunks += 1
            logger.warning("音频缓冲队列已满，丢弃 1 个音频块；累计丢弃: {}", self._dropped_chunks)

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
            self._apply_selected_device(selected_device)
            return selected_device

        default_input_index = await asyncio.to_thread(sd.default.device.__getitem__, 0)
        if default_input_index is not None and default_input_index >= 0:
            for device in devices:
                if device.index == int(default_input_index):
                    self._apply_selected_device(device)
                    return device

        selected_device = devices[0]
        self._apply_selected_device(selected_device)
        return selected_device

    def _find_matching_device(
        self,
        devices: Sequence[InputDeviceInfo],
        *,
        device_name: str | None,
        device_index: int | None,
    ) -> InputDeviceInfo | None:
        if device_index is not None:
            return next((device for device in devices if device.index == device_index), None)

        if device_name is None:
            return None

        exact_match = next((device for device in devices if device.name == device_name), None)
        if exact_match is not None:
            return exact_match

        normalized_name = device_name.casefold()
        return next((device for device in devices if normalized_name in device.name.casefold()), None)

    def _apply_selected_device(self, device: InputDeviceInfo) -> None:
        self._device_info = device
        self.config.device_name = device.name
        self.config.device_index = device.index

    def _normalize_input_devices(self, devices: Sequence[object]) -> list[InputDeviceInfo]:
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

                default_samplerate = float(raw_device["default_samplerate"])

                normalized_device = InputDeviceInfo(
                    index=index,
                    name=name,
                    max_input_channels=max_input_channels,
                    default_samplerate=default_samplerate,
                    hostapi=raw_device["hostapi"],
                )
            except ValueError:
                logger.exception("解析输入设备信息失败，已跳过: {}", raw_device)
                continue

            normalized_devices.append(normalized_device)
        return normalized_devices

    def _is_raw_input_device_info(self, raw_device: object) -> TypeGuard[_RawInputDeviceInfo]:
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

    def _require_queue(self) -> asyncio.Queue[AudioChunk]:
        queue = self._queue
        if queue is None:
            raise RuntimeError("音频输入服务尚未初始化")
        return queue

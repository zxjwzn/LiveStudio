"""基于麦克风输入的嘴型同步控制器。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import numpy as np

from livestudio.log import logger
from livestudio.services.audio_stream import AudioChunk

from ..models import AnimationType, MouthSyncControllerConfig
from .base import AnimationController

if TYPE_CHECKING:
    from ..service import AnimationRuntimeService


class MouthSyncController(AnimationController[MouthSyncControllerConfig]):
    """根据麦克风实时输入驱动嘴部参数。"""

    def __init__(
        self,
        runtime: AnimationRuntimeService,
        name: str,
        config: MouthSyncControllerConfig,
    ) -> None:
        super().__init__(runtime, name, config)
        self._smoothed_value = config.closed_value

    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        audio_stream = self.runtime.audio_stream
        if audio_stream is None:
            logger.debug("嘴型同步控制器未绑定音频流，等待下一轮")
            await asyncio.sleep(self.config.update_interval)
            return

        try:
            chunk = await audio_stream.read_chunk(
                timeout=max(self.config.update_interval * 2.0, 0.1),
            )
        except TimeoutError:
            logger.debug("嘴型同步控制器暂未收到音频块，等待下一轮")
            await asyncio.sleep(self.config.update_interval)
            return

        target_value = self._calculate_target_value(chunk)
        duration = (
            self.config.attack_duration
            if target_value > self._smoothed_value
            else self.config.release_duration
        )
        self._smoothed_value = target_value

        await self.runtime.vtubestudio.tween.tween(
            parameter_name=self.config.parameter,
            end_value=target_value,
            duration=duration,
            easing="linear",
            priority=self.config.priority,
            keep_alive=True,
        )

        await asyncio.sleep(self.config.update_interval)

    async def execute(self, **kwargs: object) -> None:
        _ = kwargs
        try:
            await self._run_idle_loop()
        finally:
            await self.runtime.vtubestudio.tween.tween(
                parameter_name=self.config.parameter,
                end_value=self.config.closed_value,
                duration=self.config.release_duration,
                easing="linear",
                priority=self.config.priority,
                keep_alive=True,
            )
            await self.runtime.vtubestudio.tween.release(self.config.parameter)

    def _calculate_target_value(self, chunk: AudioChunk) -> float:
        rms = self._calculate_rms(chunk)
        normalized_level = self._normalize_level(rms)
        speaking_floor = (
            self.config.open_min if normalized_level > 0.0 else self.config.closed_value
        )
        raw_value = speaking_floor + normalized_level * (
            self.config.open_max - speaking_floor
        )
        smoothed_value = (
            self._smoothed_value
            + (raw_value - self._smoothed_value) * self.config.smoothing_factor
        )
        return min(self.config.open_max, max(self.config.closed_value, smoothed_value))

    def _calculate_rms(self, chunk: AudioChunk) -> float:
        samples = np.asarray(chunk.data, dtype=np.float32)
        if samples.size == 0:
            return 0.0
        flattened = samples.reshape(-1)
        return float(np.sqrt(np.mean(np.square(flattened))))

    def _normalize_level(self, rms: float) -> float:
        if rms <= self.config.noise_floor:
            return 0.0
        normalized = (rms - self.config.noise_floor) / (
            self.config.voice_ceiling - self.config.noise_floor
        )
        return min(1.0, max(0.0, normalized))

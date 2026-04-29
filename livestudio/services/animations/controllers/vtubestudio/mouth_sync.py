"""基于音频响度的 VTube Studio 嘴部开合同步控制器。"""

from __future__ import annotations

import asyncio

import numpy as np
from numpy.typing import NDArray

from livestudio.log import logger
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.audio_stream import (
    AudioChunk,
    AudioChunkSubscription,
    AudioStreamSource,
)
from livestudio.tween import TweenRequest

from ..base import AnimationController
from ..config import MouthSyncControllerSettings
from ..models import AnimationType
from .constants import MOUTH_OPEN_PARAMETER


class MouthSyncController(AnimationController[MouthSyncControllerSettings]):
    """根据音频响度实时驱动 MouthOpen。"""

    def __init__(
        self,
        runtime: PlatformAnimationRuntime,
        name: str,
        config: MouthSyncControllerSettings,
        audio_stream: AudioStreamSource,
    ) -> None:
        super().__init__(runtime, name, config)
        self._audio_stream = audio_stream
        self._audio_subscription: AudioChunkSubscription = self._audio_stream.subscribe(
            queue_maxsize=8,
        )
        self._current_open = self._closed_open

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """读取一段音频并按响度更新嘴部开合。"""

        target_open = self._closed_open
        try:
            chunk = await asyncio.wait_for(
                self._audio_subscription.queue.get(),
                timeout=max(self.config.update_interval * 2.0, 0.1),
            )
            target_open = self._analyze_open(chunk)
        except TimeoutError:
            logger.debug("嘴部同步控制器暂未收到音频块，回到闭嘴状态")

        previous_open = self._current_open
        smoothed_open = self._smooth_open(target_open)
        await self._apply_open(
            smoothed_open,
            is_opening=smoothed_open >= previous_open,
        )
        await asyncio.sleep(self.config.update_interval)

    async def execute(self, **kwargs: object) -> None:
        """idle 控制器不执行一次性动画。"""

        _ = kwargs

    async def stop(self) -> None:
        await super().stop()
        self._audio_stream.unsubscribe(self._audio_subscription)

    async def stop_without_wait(self) -> None:
        await super().stop_without_wait()
        self._audio_stream.unsubscribe(self._audio_subscription)

    @property
    def _closed_open(self) -> float:
        return self._clamp01(0.0)

    def _analyze_open(self, chunk: AudioChunk) -> float:
        samples = self._to_mono_float32(chunk)
        if samples.size == 0:
            return self._closed_open

        rms = float(np.sqrt(np.mean(np.square(samples))))
        normalized_level = self._normalize_level(rms)
        if normalized_level <= 0.0:
            return self._closed_open

        return self._clamp01(
            self.config.open_min
            + normalized_level * (self.config.open_max - self.config.open_min),
        )

    def _normalize_level(self, rms: float) -> float:
        if rms <= self.config.noise_floor:
            return 0.0
        normalized = (rms - self.config.noise_floor) / (
            self.config.voice_ceiling - self.config.noise_floor
        )
        return self._clamp01(normalized)

    def _smooth_open(self, target_open: float) -> float:
        target = self._clamp01(target_open)
        self._current_open = self._clamp01(
            self._current_open
            + (target - self._current_open) * self.config.open_smoothing,
        )
        return self._current_open

    async def _apply_open(self, open_value: float, *, is_opening: bool) -> None:
        duration = (
            self.config.attack_duration if is_opening else self.config.release_duration
        )
        await self.runtime.platform.tween.tween(
            TweenRequest(
                parameter_name=MOUTH_OPEN_PARAMETER,
                end_value=self._clamp01(open_value),
                duration=duration,
                easing="linear",
                priority=self.config.priority,
                keep_alive=True,
            ),
        )

    @staticmethod
    def _to_mono_float32(chunk: AudioChunk) -> NDArray[np.float32]:
        samples = np.asarray(chunk.data, dtype=np.float32)
        if samples.size == 0:
            return np.asarray([], dtype=np.float32)
        if samples.ndim == 1:
            return samples.reshape(-1)
        return np.mean(samples, axis=1, dtype=np.float32).reshape(-1)

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

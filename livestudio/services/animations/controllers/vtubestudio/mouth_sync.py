"""基于音频响度的 VTube Studio 嘴部开合同步控制器。"""

from __future__ import annotations

import asyncio

from livestudio.log import logger
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.audio_stream import (
    AudioChunk,
    AudioChunkSubscription,
    AudioStreamSource,
)
from livestudio.tween import Easing, TweenRequest

from ..base import AnimationController
from ..config import MouthSyncControllerSettings
from ..models import AnimationType


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
        self._audio_subscription: AudioChunkSubscription | None = None
        self._current_open = 0.0

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型。"""

        return AnimationType.IDLE

    async def start(self, **kwargs: object) -> bool:
        if not self.enabled or self.is_running:
            return await super().start(**kwargs)

        self._audio_subscription = self._audio_stream.subscribe(queue_maxsize=8)
        self._current_open = self._closed_open
        started = await super().start(**kwargs)
        if not started:
            self._release_subscription()
        return started

    async def run_cycle(self) -> None:
        """读取一段音频并按响度更新嘴部开合。"""

        subscription = self._audio_subscription
        if subscription is None:
            await asyncio.sleep(self.config.update_interval)
            return

        target_open = self._closed_open
        try:
            chunk = await asyncio.wait_for(
                subscription.queue.get(),
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
        self._release_subscription()

    async def stop_without_wait(self) -> None:
        await super().stop_without_wait()
        self._release_subscription()

    def _release_subscription(self) -> None:
        subscription = self._audio_subscription
        self._audio_subscription = None
        if subscription is not None:
            self._audio_stream.unsubscribe(subscription)

    @property
    def _closed_open(self) -> float:
        return self._clamp01(0.0)

    def _analyze_open(self, chunk: AudioChunk) -> float:
        rms = chunk.analysis.rms
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
                parameter_name="MouthOpen",
                end_value=self._clamp01(open_value),
                duration=duration,
                easing=Easing.linear,
                priority=self.config.priority,
                keep_alive=True,
            ),
        )

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

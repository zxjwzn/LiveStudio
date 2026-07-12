"""各平台都能用的口型同步控制器"""

import asyncio

from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.audio_stream import (
    AudioChunk,
    AudioChunkSubscription,
    AudioStreamSource,
)
from livestudio.services.semantic_actions import SemanticAction, SemanticTweenRequest
from livestudio.services.tween import Easing
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import MouthSyncControllerSettings
from ..constants import MOUTH_SYNC_PRIORITY, MOUTH_SYNC_YIELD_PRIORITY
from ..models import AnimationType


class MouthSyncController(AnimationController[MouthSyncControllerSettings]):
    """根据音频响度实时驱动嘴部张开语义动作"""

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
        """控制器类型"""

        return AnimationType.IDLE

    async def start(self, **kwargs: object) -> bool:
        if self.is_running:
            return False

        self._audio_subscription = self._audio_stream.subscribe(queue_maxsize=8)
        self._current_open = self._closed_open
        try:
            started = await super().start(**kwargs)
        except BaseException:
            self._release_subscription()
            raise
        if not started:
            self._release_subscription()
        return started

    async def run_cycle(self) -> None:
        """读取一段音频并按响度更新嘴部开合"""

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
        # 音量过低(目标开度为 0,即静音/无音频)时让出优先级,使其他请求(如表情解算
        # EXPRESSION_AU_PRIORITY=20)可接管 MOUTH_OPEN;说话时(目标 > 0)保持高优先级
        # (MOUTH_SYNC_PRIORITY)独占唇形同步。
        # 让出后本控制器后续仍以让出优先级发布闭嘴,但被更高优先级占用时会被 _try_acquire
        # 拒绝、不会反复抢回(让出值 < 对方优先级)。
        priority = MOUTH_SYNC_YIELD_PRIORITY if target_open <= self._closed_open else MOUTH_SYNC_PRIORITY
        await self._apply_open(
            smoothed_open,
            is_opening=smoothed_open >= previous_open,
            priority=priority,
        )
        await asyncio.sleep(self.config.update_interval)

    async def stop(self) -> None:
        await super().stop()
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
            normalized_level * self.config.open_amplitude,
        )

    def _normalize_level(self, rms: float) -> float:
        if rms <= self.config.noise_floor:
            return 0.0
        normalized = (rms - self.config.noise_floor) / (self.config.voice_ceiling - self.config.noise_floor)
        return self._clamp01(normalized)

    def _smooth_open(self, target_open: float) -> float:
        target = self._clamp01(target_open)
        self._current_open = self._clamp01(
            self._current_open + (target - self._current_open) * self.config.open_smoothing,
        )
        return self._current_open

    async def _apply_open(self, open_value: float, *, is_opening: bool, priority: int) -> None:
        duration = self.config.attack_duration if is_opening else self.config.release_duration
        await self.runtime.platform.tween_semantic(
            [
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.MOUTH_OPEN,
                    end_value=self._clamp01(open_value),
                    duration=duration,
                    easing=Easing.linear,
                    priority=priority,
                ),
            ],
        )

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

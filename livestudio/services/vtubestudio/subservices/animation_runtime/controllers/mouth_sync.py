"""基于音频输入的三参数嘴型同步控制器。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from livestudio.log import logger

from ..models import AnimationType, MouthSyncControllerConfig
from ..mouth_sync import (
    MouthPose,
    MouthPoseParameterMapper,
    MouthPoseSmoother,
    SpectralMouthPoseAnalyzer,
)
from .base import AnimationController

if TYPE_CHECKING:
    from ..service import AnimationRuntimeService


class MouthSyncController(AnimationController[MouthSyncControllerConfig]):
    """根据音频实时输入驱动 MouthOpen、MouthSmile 与 MouthX。"""

    def __init__(
        self,
        runtime: AnimationRuntimeService,
        name: str,
        config: MouthSyncControllerConfig,
    ) -> None:
        super().__init__(runtime, name, config)
        initial_pose = self._build_closed_pose()
        self._analyzer = SpectralMouthPoseAnalyzer(config)
        self._smoother = MouthPoseSmoother(initial_pose, config)
        self._mapper = MouthPoseParameterMapper(config)

    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        audio_stream = self.runtime.audio_stream
        if audio_stream is None:
            logger.debug("嘴型同步控制器未绑定音频流，等待下一轮")
            await self._apply_pose(self._smoother.smooth(self._build_closed_pose()))
            await asyncio.sleep(self.config.update_interval)
            return

        try:
            chunk = await audio_stream.read_chunk(
                timeout=max(self.config.update_interval * 2.0, 0.1),
            )
        except TimeoutError:
            logger.debug("嘴型同步控制器暂未收到音频块，等待下一轮")
            await self._apply_pose(self._smoother.smooth(self._build_closed_pose()))
            await asyncio.sleep(self.config.update_interval)
            return

        target_pose = self._analyzer.analyze(chunk)
        smoothed_pose = self._smoother.smooth(target_pose)
        await self._apply_pose(smoothed_pose)
        await asyncio.sleep(self.config.update_interval)

    async def execute(self, **kwargs: object) -> None:
        _ = kwargs
        try:
            await self._run_idle_loop()
        finally:
            closed_pose = self._build_closed_pose()
            await self._apply_pose(closed_pose)
            await self.runtime.vtubestudio.tween.release_many(
                self._mapper.parameter_names,
            )

    async def _apply_pose(self, pose: MouthPose) -> None:
        await self.runtime.vtubestudio.tween.set_values(
            self._mapper.to_values(pose),
            priority=self.config.priority,
            keep_alive=True,
        )

    def _build_closed_pose(self) -> MouthPose:
        return MouthPose(
            open=self.config.closed_pose.open,
            smile=self.config.closed_pose.smile,
            x=self.config.closed_pose.x,
        ).clamp()

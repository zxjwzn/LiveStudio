"""统一音频流路由器"""

import asyncio
import contextlib

import numpy as np

from livestudio.config import ConfigManager
from livestudio.utils.log import logger
from livestudio.utils.paths import config_path

from .base import AudioStreamSource
from .config import AudioStreamRouterConfig
from .models import (
    AudioChunk,
    AudioChunkSubscription,
    AudioSourceKind,
)
from .sources import MicrophoneAudioStreamSource, TTSAudioStreamSource
from .sources.microphone.models import InputDeviceInfo


class AudioStreamRouter(AudioStreamSource):
    """在多个音频源之间选择唯一活动源"""

    def __init__(
        self,
    ) -> None:
        super().__init__()
        self.config_manager = ConfigManager(
            AudioStreamRouterConfig,
            config_path("audio_stream.yaml"),
        )
        self._microphone_source: MicrophoneAudioStreamSource | None = None
        self._tts_source: TTSAudioStreamSource | None = None
        self._sources: dict[AudioSourceKind, AudioStreamSource] = {}
        self._active_source_kind: AudioSourceKind | None = None
        self._source_subscription: AudioChunkSubscription | None = None
        self._forward_task: asyncio.Task[None] | None = None
        self._shutdown_task: asyncio.Task[None] | None = None

    @property
    def config(self) -> AudioStreamRouterConfig:
        return self.config_manager.config

    @property
    def active_source_kind(self) -> AudioSourceKind:
        if self._active_source_kind is None:
            raise RuntimeError("音频流路由器尚未激活任何音频源")
        return self._active_source_kind

    @property
    def active_source(self) -> AudioStreamSource:
        if self._active_source_kind is None or self._sources.get(self._active_source_kind) is None:
            raise RuntimeError("音频流路由器当前没有可用的活动音频源")
        return self._sources[self._active_source_kind]

    @property
    def microphone_source(self) -> MicrophoneAudioStreamSource:
        """返回内置麦克风音频源"""

        if self._microphone_source is None:
            raise RuntimeError("音频流路由器尚未启动")
        return self._microphone_source

    async def list_input_devices(self) -> list[InputDeviceInfo]:
        """枚举系统输入设备，与路由器生命周期解耦。

        列设备是纯系统查询（sd.query_devices），不依赖音频管线是否已初始化/运行。
        有现成麦克风源就复用，否则临时建一个只用于查询——这样即便活动源打不开
        （设备被占用/拔出导致 start 回滚销毁了管线），设备下拉仍能正常列出，
        用户得以换一个可用设备再重启。
        """

        source = self._microphone_source or MicrophoneAudioStreamSource(self.config.microphone)
        return await source.list_input_devices()

    @property
    def tts_source(self) -> TTSAudioStreamSource:
        """返回内置 TTS 音频源"""

        if self._tts_source is None:
            raise RuntimeError("音频流路由器尚未启动")
        return self._tts_source

    async def _do_start(self) -> None:
        await self._ensure_sources_built()
        await self.active_source.start()
        self._forward_task = asyncio.create_task(self._forward_chunks())

    async def _ensure_sources_built(self) -> None:
        """重读配置并构建音频源与活动源订阅（幂等：已构建则跳过）。

        资源准备并入启动流程；switch_source 也复用，确保在路由器尚未启动时也能
        先把源建好再切换。
        """

        if self._sources:
            return
        await self.config_manager.load()

        self._microphone_source = MicrophoneAudioStreamSource(self.config.microphone)
        self._tts_source = TTSAudioStreamSource(self.config.tts)
        self._sources = {
            AudioSourceKind.MICROPHONE: self._microphone_source,
            AudioSourceKind.TTS: self._tts_source,
        }
        self._active_source_kind = self.config.source
        self._source_subscription = self.active_source.subscribe(
            queue_maxsize=self.config.queue_maxsize,
        )
        logger.info("音频流路由器音频源已就绪，当前音频源: {}", self.active_source_kind)

    async def _do_stop(self) -> None:
        """停止并释放音频流路由器资源（唯一真正的退出入口）。"""

        await self._stop_forward_task()
        if self._source_subscription is not None:
            self.active_source.unsubscribe(self._source_subscription)
            self._source_subscription = None

        for source in self._sources.values():
            await source.stop()
        self._clear_subscriptions()
        await self.config_manager.save()
        self._microphone_source = None
        self._tts_source = None
        self._sources = {}
        self._active_source_kind = None

    async def _do_restart(self) -> None:
        """软重启：就地重启当前活动源（换设备等配置生效），保留对外契约。

        委托给活动源自身的 ``restart()``——源的软重启只回收/重建物理流而**不**清空
        其订阅，因此路由器对该源的转发订阅 ``_source_subscription`` 与转发任务都得以
        存活，路由器对外的下游订阅者（如 MouthSyncController）更不受影响。这正是
        统一生命周期里 restart 的语义：只有 stop 才真正断开对外契约。
        """

        await self.active_source.restart()
        logger.info("音频流路由器已就地重启活动音频源: {}", self._active_source_kind)

    async def switch_source(
        self,
        source_kind: AudioSourceKind,
    ) -> None:
        if self._active_source_kind == source_kind:
            return
        await self._ensure_sources_built()

        was_started = self.is_started
        previous_source_kind = self._active_source_kind
        if previous_source_kind is None:
            raise RuntimeError("音频流路由器当前没有可回滚的活动音频源")
        if was_started:
            await self._stop_forward_task()
            await self.active_source.stop()
        self._rebind_active_source(source_kind)
        await self.config_manager.save()

        if was_started:
            try:
                # 源在上一次切走时已 stop（麦克风会清空 _loop/_device_info），
                # start() 会按 Mixin 约定重新解析设备并打开物理流。
                await self.active_source.start()
            except Exception:
                self._rebind_active_source(previous_source_kind)
                await self.active_source.start()
                self._forward_task = asyncio.create_task(self._forward_chunks())
                await self.config_manager.save()
                raise
            self._forward_task = asyncio.create_task(self._forward_chunks())

        logger.info("音频流路由器已切换音频源: {}", source_kind)

    def _rebind_active_source(self, source_kind: AudioSourceKind) -> None:
        """切换活动源标识并重建对该源的订阅。"""

        if self._source_subscription is not None:
            self.active_source.unsubscribe(self._source_subscription)
            self._source_subscription = None
        self._active_source_kind = source_kind
        self.config.source = source_kind
        self._source_subscription = self.active_source.subscribe(
            queue_maxsize=self.config.queue_maxsize,
        )

    async def _stop_forward_task(self) -> None:
        task = self._forward_task
        self._forward_task = None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _forward_chunks(self) -> None:
        """将当前活动源的音频块广播给路由器订阅者"""

        source_subscription = self._source_subscription
        if source_subscription is None:
            raise RuntimeError("音频流路由器尚未订阅活动音频源")
        try:
            while True:
                chunk = await source_subscription.queue.get()
                self._chunk_analysis(chunk)
                self._publish_chunk(chunk)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("音频流路由器转发任务异常，触发停机以回收资源")
            # 在独立任务里停机：stop() 会 cancel 本转发任务并 await，
            # 若在此直接 await self.stop() 会变成任务等待取消自身而死锁。
            # 持有引用避免任务被 GC 回收，并通过回调记录 stop() 自身异常。
            self._shutdown_task = asyncio.get_running_loop().create_task(self.stop())
            self._shutdown_task.add_done_callback(self._on_shutdown_done)

    def _on_shutdown_done(self, task: asyncio.Task[None]) -> None:
        """转发任务触发的自动停机完成回调：清理句柄并记录失败。"""

        self._shutdown_task = None
        if task.cancelled():
            return
        if (exc := task.exception()) is not None:
            logger.error("音频流路由器自动停机失败: {}", exc)

    @staticmethod
    def _chunk_analysis(chunk: AudioChunk) -> None:
        """补充音频块通用分析结果，避免下游消费者重复计算"""

        samples = np.asarray(chunk.data, dtype=np.float32)
        if samples.size == 0:
            rms = 0.0
            peak = 0.0
        else:
            flattened = samples.reshape(-1)
            rms = float(np.sqrt(np.mean(np.square(flattened))))
            peak = float(np.max(np.abs(flattened)))
        chunk.analysis.rms = rms
        chunk.analysis.peak = peak

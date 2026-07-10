"""音频桥接:实时电平 + 设备枚举 + 设备配置保存

订阅路由器音频块,在 drain 任务里持续取块,用定时器节流后以信号发出电平(避免逐块
刷新导致重排)。设备枚举与生命周期解耦。保存设备配置走「写盘 → reload_source」,
因为 mic source 在初始化时绑定 config 对象,故需重建实例而非 restart;reload_source 不清空路由器对外下游订阅(MouthSyncController 等),避免保存后唇形同步收不到音频块。
"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QTimer, Signal

from livestudio.gui.components.config_editor import ChoiceItem
from livestudio.gui.constants import AUDIO_METER_INTERVAL_MS
from livestudio.services import AudioSourceKind, AudioStreamRouter
from livestudio.services.audio_stream.config import MicrophoneAudioStreamConfig
from livestudio.services.audio_stream.models import AudioChunkSubscription
from livestudio.services.audio_stream.playback import PlaybackConfig
from livestudio.services.audio_stream.sources.tts.config import TTSAudioStreamConfig
from livestudio.utils.log import logger


class AudioController(QObject):
    """音频路由的 GUI 桥接:电平推送、设备列表、配置保存、音源切换/重载"""

    levelChanged = Signal(float, float, bool)  # rms, peak, overflowed
    devicesReloaded = Signal()
    saveSucceeded = Signal()
    saveFailed = Signal(str)
    sourceChanged = Signal(str)  # AudioSourceKind.value
    reloadSucceeded = Signal()
    reloadFailed = Signal(str)
    # 本机播放保存专用反馈(独立成页,避免与音频页共享 saveSucceeded/saveFailed 串扰)
    playbackSaveSucceeded = Signal()
    playbackSaveFailed = Signal(str)

    def __init__(self, router: AudioStreamRouter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._router = router
        self._subscription: AudioChunkSubscription | None = None
        self._drain_task: asyncio.Task[None] | None = None

        self._latest_rms = 0.0
        self._latest_peak = 0.0
        self._latest_overflow = False

        self._timer = QTimer(self)
        self._timer.setInterval(AUDIO_METER_INTERVAL_MS)
        self._timer.timeout.connect(self._emit_level)

    def start_metering(self) -> None:
        """开始订阅音频块并按节流频率推送电平"""

        if self._subscription is not None:
            return
        self._subscription = self._router.subscribe(queue_maxsize=32)
        self._drain_task = asyncio.ensure_future(self._drain())
        self._timer.start()

    def stop_metering(self) -> None:
        """停止推送并退订"""

        self._timer.stop()
        if self._drain_task is not None:
            self._drain_task.cancel()
            self._drain_task = None
        if self._subscription is not None:
            self._router.unsubscribe(self._subscription)
            self._subscription = None

    async def _drain(self) -> None:
        subscription = self._subscription
        if subscription is None:
            return
        while True:
            chunk = await subscription.queue.get()
            self._latest_rms = chunk.analysis.rms
            self._latest_peak = chunk.analysis.peak
            self._latest_overflow = chunk.overflowed

    def _emit_level(self) -> None:
        self.levelChanged.emit(self._latest_rms, self._latest_peak, self._latest_overflow)

    async def list_device_choices(self) -> list[ChoiceItem]:
        """枚举输入设备为下拉候选(显示设备名 → 写回设备索引)。

        设备的实际选用由 index 决定(name 可能重复/不稳定)。附「系统默认」选项写回
        None,表示交给后端自动选择当前默认输入设备。
        """

        devices = await self._router.list_input_devices()
        choices: list[ChoiceItem] = [("系统默认", None)]
        choices.extend((f"[{device.index}] {device.name}", device.index) for device in devices)
        return choices

    async def save_microphone_config(self, config: MicrophoneAudioStreamConfig) -> None:
        """保存麦克风配置并重建麦克风源实例,使新设备即时生效。

        用 reload_source 而非 stop+start:后者会清空路由器对外下游订阅(MouthSyncController),
        导致保存后唇形同步收不到音频块。reload_source 只重建内部源实例,保留下游订阅与
        本机播放 sink。mic source 在初始化时绑定 config 对象,故需重建实例而非 restart。
        """

        try:
            self._router.config.microphone = config
            await self._router.config_manager.save()
            if self._router.is_started:
                await self._router.reload_source(AudioSourceKind.MICROPHONE)
        except Exception as exc:
            logger.exception("保存麦克风配置失败")
            self.saveFailed.emit(str(exc))
            return
        self.saveSucceeded.emit()

    def active_source(self) -> AudioSourceKind:
        """当前激活音源;路由未激活时回落配置里的 source"""

        try:
            return self._router.active_source_kind
        except RuntimeError:
            return self._router.config.source

    def microphone_config(self) -> MicrophoneAudioStreamConfig:
        """当前麦克风配置快照"""

        return self._router.config.microphone

    def tts_config(self) -> TTSAudioStreamConfig:
        """当前 TTS 配置快照"""

        return self._router.config.tts

    async def switch_source(self, kind: AudioSourceKind) -> None:
        """切换激活音源并保存为默认;切换期间重挂电平表"""

        try:
            if self.active_source() == kind and self._router.is_started:
                return
            self.stop_metering()
            await self._router.switch_source(kind)
            self._router.config.source = kind
            await self._router.config_manager.save()
            self.start_metering()
        except Exception as exc:
            logger.exception("切换音源失败")
            self.reloadFailed.emit(str(exc))
            return
        self.sourceChanged.emit(kind.value)

    async def reload_source(self) -> None:
        """重载当前音源(就地重建物理流,如换设备/恢复中断)"""

        try:
            self.stop_metering()
            await self._router.restart()
            self.start_metering()
        except Exception as exc:
            logger.exception("重载音源失败")
            self.reloadFailed.emit(str(exc))
            return
        self.reloadSucceeded.emit()

    async def save_tts_config(self, config: TTSAudioStreamConfig) -> None:
        """保存 TTS 配置并重建 TTS 源实例(若为活动源则重绑转发),保留下游订阅。

        用 reload_source 而非 stop+start,原因同 save_microphone_config。无论 TTS 是否为
        活动源都重建实例,使新配置在下次切换到 TTS 时即生效(不必整路由器重启)。
        """

        try:
            self._router.config.tts = config
            await self._router.config_manager.save()
            if self._router.is_started:
                await self._router.reload_source(AudioSourceKind.TTS)
        except Exception as exc:
            logger.exception("保存 TTS 配置失败")
            self.saveFailed.emit(str(exc))
            return
        self.saveSucceeded.emit()

    def playback_config(self) -> PlaybackConfig:
        """当前本机播放配置快照"""

        return self._router.config.playback

    async def list_output_device_choices(self) -> list[ChoiceItem]:
        """枚举输出设备为下拉候选(显示设备名 -> 写回设备索引),附「系统默认」写回 None"""

        devices = await self._router.list_output_devices()
        choices: list[ChoiceItem] = [("系统默认", None)]
        choices.extend((f"[{device.index}] {device.name}", device.index) for device in devices)
        return choices

    async def save_playback_config(self, config: PlaybackConfig) -> None:
        """保存本机播放配置并重建播放订阅方,使新输出设备/过滤源/音量即时生效"""

        try:
            self._router.config.playback = config
            await self._router.config_manager.save()
            await self._router.apply_playback_config()
        except Exception as exc:
            logger.exception("保存本机播放配置失败")
            self.playbackSaveFailed.emit(str(exc))
            return
        self.playbackSaveSucceeded.emit()

    async def speak_test(self, text: str = "测试") -> None:
        """触发一次 TTS 发声(占位正弦音),验证"总线接管 -> 本机播放 + 唇形"管道。

        真实 engine 接入后由 engine 消费 text;此处仅占位发声。
        """

        await self._router.speak(text)

    def stop_speaking(self) -> None:
        """停止进行中的 TTS 发声"""

        self._router.stop_speaking()

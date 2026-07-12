"""音频桥接:实时电平 + 设备枚举 + 设备配置保存

订阅路由器音频块,在 drain 任务里持续取块,用定时器节流后以信号发出电平(避免逐块
刷新导致重排)。设备枚举与生命周期解耦。保存设备配置走「写盘 → reload_source」,
因为 mic source 在初始化时绑定 config 对象,故需重建实例而非 restart;reload_source 不清空路由器对外下游订阅(MouthSyncController 等),避免保存后唇形同步收不到音频块。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, cast

from PySide6.QtCore import QObject, QTimer, Signal

from livestudio.gui.components.config_editor import ChoiceItem
from livestudio.gui.constants import AUDIO_METER_INTERVAL_MS
from livestudio.services import AudioSourceKind, AudioStreamRouter
from livestudio.services.animations.controllers.config import TTSpeakControllerSettings
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
    # 音频播放保存专用反馈(独立成页,避免与音频页共享 saveSucceeded/saveFailed 串扰)
    playbackSaveSucceeded = Signal()
    playbackSaveFailed = Signal(str)
    # 平台模型切换(转发自平台 bridge):当前模型 TTS 发声配置可能变了,音频页据此刷新
    modelChanged = Signal()
    # 平台连接态(转发自平台 bridge):未连接时音频页隐藏当前模型 TTS 发声段
    platformConnected = Signal(bool)
    # 当前模型 TTS 发声配置保存专用反馈(独立于音频页 saveSucceeded/saveFailed,避免串扰)
    ttsSpeakSaveSucceeded = Signal()
    ttsSpeakSaveFailed = Signal(str)

    def __init__(self, router: AudioStreamRouter, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._router = router
        self._speak_app: object | None = None
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
        音频播放 sink。mic source 在初始化时绑定 config 对象,故需重建实例而非 restart。
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

    def _speak_platform(self) -> Any:
        """注入的 speak app 的 platform 对象(duck-type);无 app/无 platform 返回 None。

        返回 Any 以便调用方访问 model_config 等属性(保持平台无关,不 import 具体平台类型)。
        """
        app = self._speak_app
        if app is None:
            return None
        return getattr(app, "platform", None)

    def current_tts_speak(self) -> TTSpeakControllerSettings | None:
        """当前模型的 TTS 发声配置(激活供应商音色);未连接/未加载模型返回 None。"""

        platform = self._speak_platform()
        if platform is None:
            return None
        try:
            return platform.model_config.controllers.tts_speak
        except RuntimeError:
            return None

    async def save_tts_speak(self, speak: TTSpeakControllerSettings) -> None:
        """保存当前模型的 TTS 发声配置:写回模型配置并落盘(同步内存快照,单源事实)。

        经 app.platform.model_config_manager.path 取当前模型路径,save_model_config 同步内存再落盘,
        使重连/停机 save() 不用旧快照覆盖。失败 emit ttsSpeakSaveFailed,成功 emit ttsSpeakSaveSucceeded。
        """

        try:
            platform = self._speak_platform()
            if platform is None:
                raise RuntimeError("无可用平台(请先连接)")
            model_config = platform.model_config  # 无已加载模型时抛 RuntimeError
            updated = model_config.model_copy(update={
                "controllers": model_config.controllers.model_copy(update={"tts_speak": speak}),
            })
            await platform.save_model_config(platform.model_config_manager.path, updated)
        except Exception as exc:
            logger.exception("保存 TTS 发声配置失败")
            self.ttsSpeakSaveFailed.emit(str(exc))
            return
        self.ttsSpeakSaveSucceeded.emit()

    def playback_config(self) -> PlaybackConfig:
        """当前音频播放配置快照"""

        return self._router.config.playback

    async def list_output_device_choices(self) -> list[ChoiceItem]:
        """枚举输出设备为下拉候选(显示设备名 -> 写回设备索引),附「系统默认」写回 None"""

        devices = await self._router.list_output_devices()
        choices: list[ChoiceItem] = [("系统默认", None)]
        choices.extend((f"[{device.index}] {device.name}", device.index) for device in devices)
        return choices

    async def save_playback_config(self, config: PlaybackConfig) -> None:
        """保存音频播放配置并重建播放订阅方,使新输出设备/过滤源/音量即时生效"""

        try:
            self._router.config.playback = config
            await self._router.config_manager.save()
            await self._router.apply_playback_config()
        except Exception as exc:
            logger.exception("保存音频播放配置失败")
            self.playbackSaveFailed.emit(str(exc))
            return
        self.playbackSaveSucceeded.emit()

    def set_speak_app(self, app: object | None) -> None:
        """注入平台 app,使测试 speak 走 app.speak -> TTSpeak 控制器(配置驱动音色)。"""

        self._speak_app = app

    async def speak(self, text: str) -> None:
        """触发一次 TTS 发声:经注入的平台 app -> TTSpeak 控制器。

        需已注入 app(service_bridge 注册首个平台 app)且该平台已连接加载模型;否则抛错,
        由调用方(run_guarded)呈现。统一经控制器触发,不再直连 tts_source。
        """

        app = self._speak_app
        if app is None:
            raise RuntimeError("TTS 测试需要一个已连接的平台(请先连接并加载模型)")
        speak = getattr(app, "speak", None)
        if not callable(speak):
            raise TypeError("注入的平台 app 不支持 speak")
        await cast(Callable[[str], Awaitable[None]], speak)(text)

    async def stop_speaking(self) -> None:
        """停止进行中的 TTS 发声:经注入的平台 app -> TTSpeak 控制器。"""

        app = self._speak_app
        stop = getattr(app, "stop_speaking", None) if app is not None else None
        if callable(stop):
            await cast(Callable[[], Awaitable[None]], stop)()

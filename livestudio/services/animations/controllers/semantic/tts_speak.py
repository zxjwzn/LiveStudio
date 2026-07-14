"""TTS 发声 oneshot 控制器。

控制器把运行时文本和供应商配置合并为 ``TtsSpeakRequest``，再交给 TTS 源。
"""

from __future__ import annotations

import contextlib

from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.audio_stream import AudioStreamRouter, AudioStreamSource
from livestudio.services.audio_stream.models import AudioSourceKind
from livestudio.services.audio_stream.sources.tts.engines import TTS_ENGINES
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import TTSpeakControllerSettings
from ..models import AnimationType


class TTSpeakController(AnimationController[TTSpeakControllerSettings]):
    """一次性 TTS 发声:配置驱动音色,kwargs 传入文本"""

    def __init__(
        self,
        runtime: PlatformAnimationRuntime,
        name: str,
        config: TTSpeakControllerSettings,
        audio_stream: AudioStreamSource,
    ) -> None:
        super().__init__(runtime, name, config)
        self._audio_stream = audio_stream

    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.ONESHOT

    def _tts_router(self) -> AudioStreamRouter:
        stream = self._audio_stream
        if isinstance(stream, AudioStreamRouter):
            return stream
        if all(hasattr(stream, name) for name in ("tts_source", "switch_source", "is_started", "config")):
            return stream  # type: ignore[return-value]
        raise RuntimeError("TTSpeak 需要 AudioStreamRouter 作为 audio_stream")

    async def execute(self, **kwargs: object) -> None:
        """触发一次发声。

        kwargs:
            text: str,必填
            其它键:可选覆盖激活供应商 speak 配置字段(如 Fish 的 model/reference_id/latency/speed)
        """

        text = kwargs.get("text")
        if not isinstance(text, str) or not text.strip():
            logger.warning("TTSpeak 未收到合法 text,跳过")
            return
        text = text.strip()

        subtitle = kwargs.get("subtitle", text)
        if not isinstance(subtitle, str) or not subtitle.strip():
            logger.warning("TTSpeak 未收到合法 subtitle,跳过")
            return
        request = self.config.create_speak_request(
            text=text,
            subtitle=subtitle.strip(),
            overrides=kwargs,
        )

        router = self._tts_router()
        tts_cfg = getattr(getattr(router, "config", None), "tts", None)
        if tts_cfg is not None and request.kind not in TTS_ENGINES:
            raise RuntimeError(f"未知 TTS 供应商 kind={request.kind!r}(未在 TTS_ENGINES 注册)")

        try:
            active = router.active_source_kind
        except RuntimeError:
            active = None
        if active is not AudioSourceKind.TTS and router.is_started:
            await router.switch_source(AudioSourceKind.TTS)

        await router.tts_source.speak(request)

    async def stop(self) -> None:
        if isinstance(self._audio_stream, AudioStreamRouter):
            with contextlib.suppress(RuntimeError):
                await self._audio_stream.tts_source.stop_speaking()
        await super().stop()

    async def cancel(self) -> None:
        if isinstance(self._audio_stream, AudioStreamRouter):
            with contextlib.suppress(RuntimeError):
                await self._audio_stream.tts_source.stop_speaking()
        await super().cancel()

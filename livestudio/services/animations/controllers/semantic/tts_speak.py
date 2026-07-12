"""TTS 发声 oneshot 控制器

并列 speak 配置: kind + 各供应商 speak 配置(fish_audio 等)。
execute 按 kind 取激活 speak 配置合并为 opts,校验 kind 已注册,调用 tts_source.speak。
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

        opts = self.config.as_speak_opts()
        # kwargs 覆盖已知 speak 字段(kind 不可覆盖;未知键忽略)
        for key, value in kwargs.items():
            if key in ("text", "kind") or value is None:
                continue
            if key in opts:
                opts[key] = value

        router = self._tts_router()
        tts_cfg = getattr(getattr(router, "config", None), "tts", None)
        if tts_cfg is not None:
            # 校验 kind 已注册(连接槽并列,缺密钥由引擎报错)
            kind = str(opts.get("kind", "fish_audio"))
            if kind not in TTS_ENGINES:
                raise RuntimeError(f"未知 TTS 供应商 kind={kind!r}(未在 TTS_ENGINES 注册)")

        try:
            active = router.active_source_kind
        except RuntimeError:
            active = None
        if active is not AudioSourceKind.TTS and router.is_started:
            await router.switch_source(AudioSourceKind.TTS)

        await router.tts_source.speak(text, **opts)

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

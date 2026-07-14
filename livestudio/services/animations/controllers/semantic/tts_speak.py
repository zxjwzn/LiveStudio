"""TTS 发声 oneshot 控制器

运行时入参仅 ``TTSpeakRequest``(合成文本 + 字幕文本)。
音色/供应商来自模型配置 ``TTSpeakControllerSettings``; 全局 model/latency/speed 在 TTS 连接槽。

字幕:
  - 在 speak 首帧上总线(SpeakSession.started)后才 begin + 按字速推 segments
  - 音频呈现结束(SpeakSession.ended)时,若还有未推完的字,整段剩余一次 publish 后 finish
"""

from __future__ import annotations

import asyncio
import contextlib

from pydantic import BaseModel, ConfigDict, Field, field_validator

from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.audio_stream import AudioStreamRouter, AudioStreamSource
from livestudio.services.audio_stream.models import AudioSourceKind
from livestudio.services.audio_stream.sources.tts.engines import TTS_ENGINES
from livestudio.services.audio_stream.sources.tts.session import SpeakSession
from livestudio.services.subtitle import SubtitleSegment, SubtitleStream
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import TTSpeakControllerSettings
from ..models import AnimationType


class TTSpeakRequest(BaseModel):
    """TTSpeak 单次执行入参(全部经 pydantic 校验)。

    - ``text``: 送入 TTS 合成的文本
    - ``subtitle``: 字幕全文; ``None`` 表示与 text 相同; 空串表示不推字幕
    """

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, description="合成文本(非空)")
    subtitle: str | None = Field(
        default=None,
        description="字幕全文; None=与 text 相同; 空串=不推字幕",
    )

    @field_validator("text", mode="before")
    @classmethod
    def _strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("subtitle", mode="before")
    @classmethod
    def _strip_subtitle(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    def resolved_subtitle(self) -> str | None:
        """返回应推送的字幕全文; None 表示跳过字幕。"""

        if self.subtitle is None:
            return self.text
        if not self.subtitle:
            return None
        return self.subtitle


class TTSpeakController(AnimationController[TTSpeakControllerSettings]):
    """一次性 TTS 发声 + 与音频呈现对齐的字幕推送。"""

    def __init__(
        self,
        runtime: PlatformAnimationRuntime,
        name: str,
        config: TTSpeakControllerSettings,
        audio_stream: AudioStreamSource,
    ) -> None:
        super().__init__(runtime, name, config)
        self._audio_stream = audio_stream
        self._subtitle_task: asyncio.Task[None] | None = None

    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.ONESHOT

    def _tts_router(self) -> AudioStreamRouter:
        stream = self._audio_stream
        if isinstance(stream, AudioStreamRouter):
            return stream
        if all(
            hasattr(stream, name)
            for name in ("tts_source", "switch_source", "is_started", "config", "subtitle_stream")
        ):
            return stream  # type: ignore[return-value]
        raise RuntimeError("TTSpeak 需要 AudioStreamRouter 作为 audio_stream")

    async def start(self, **kwargs: object) -> bool:
        """ONESHOT 可重入:新请求打断上一次 start 任务后立刻执行。"""

        await self._interrupt_previous()
        async with self._lifecycle_lock:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(**kwargs))
            return True

    async def _interrupt_previous(self) -> None:
        async with self._lifecycle_lock:
            task = self._task
            self._task = None
            self._stop_event.set()
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._stop_subtitle_push()
        if isinstance(self._audio_stream, AudioStreamRouter):
            with contextlib.suppress(RuntimeError):
                await self._audio_stream.tts_source.stop_speaking()

    async def execute(self, **kwargs: object) -> None:
        """触发一次发声并可选推送字幕。

        kwargs 须可校验为 ``TTSpeakRequest``(仅 text / subtitle)。
        await 到 tts.speak 启动返回(会话已挂上);字幕任务在后台与呈现对齐。
        """

        try:
            request = TTSpeakRequest.model_validate(kwargs)
        except Exception as exc:
            logger.warning("TTSpeak 入参无效,跳过: {}", exc)
            return

        tts_request = self.config.as_speak_request()
        router = self._tts_router()
        if tts_request.kind not in TTS_ENGINES:
            raise RuntimeError(f"未知 TTS 供应商 kind={tts_request.kind!r}(未在 TTS_ENGINES 注册)")

        try:
            active = router.active_source_kind
        except RuntimeError:
            active = None
        if active is not AudioSourceKind.TTS and router.is_started:
            await router.switch_source(AudioSourceKind.TTS)

        await self._stop_subtitle_push()

        session = await router.tts_source.speak(request.text, tts_request)
        subtitle_text = request.resolved_subtitle()
        if subtitle_text is None:
            return
        if not isinstance(session, SpeakSession) and not hasattr(session, "wait_started"):
            logger.warning("TTS speak 未返回会话,跳过字幕同步")
            return

        self._subtitle_task = asyncio.create_task(
            self._drive_subtitle(
                router.subtitle_stream,
                subtitle_text,
                session,  # type: ignore[arg-type]
                chars_per_second=self.config.subtitle_chars_per_second,
            ),
            name="ttspeak-subtitle",
        )

    async def _drive_subtitle(
        self,
        stream: SubtitleStream,
        text: str,
        session: SpeakSession,
        *,
        chars_per_second: float,
    ) -> None:
        """首帧后 begin,按字速推 segments;音频结束冲刷剩余并 finish。"""

        delay = 1.0 / chars_per_second if chars_per_second > 0 else 0.0
        index = 0
        t = 0.0
        try:
            await session.wait_started()
            stream.begin(text)

            while index < len(text):
                if session.ended:
                    break
                char = text[index]
                start = t
                end = t + delay
                stream.publish_segments([SubtitleSegment(text=char, start=start, end=end)])
                t = end
                index += 1
                if delay <= 0 or index >= len(text):
                    continue
                # 字间隔可被音频结束打断
                try:
                    await asyncio.wait_for(session.wait_ended(), timeout=delay)
                    break
                except TimeoutError:
                    continue

            if index < len(text):
                rest = text[index:]
                stream.publish_segments([SubtitleSegment(text=rest, start=t, end=t)])
            stream.finish()
        except asyncio.CancelledError:
            if index < len(text):
                rest = text[index:]
                with contextlib.suppress(Exception):
                    stream.publish_segments([SubtitleSegment(text=rest, start=t, end=t)])
            with contextlib.suppress(Exception):
                stream.finish()
            raise
        except Exception:
            logger.exception("字幕推送任务异常")
            with contextlib.suppress(Exception):
                stream.finish()

    async def _stop_subtitle_push(self) -> None:
        task = self._subtitle_task
        self._subtitle_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def stop(self) -> None:
        await self._stop_subtitle_push()
        if isinstance(self._audio_stream, AudioStreamRouter):
            with contextlib.suppress(RuntimeError):
                await self._audio_stream.tts_source.stop_speaking()
        await super().stop()

    async def cancel(self) -> None:
        await self._stop_subtitle_push()
        if isinstance(self._audio_stream, AudioStreamRouter):
            with contextlib.suppress(RuntimeError):
                await self._audio_stream.tts_source.stop_speaking()
        await super().cancel()

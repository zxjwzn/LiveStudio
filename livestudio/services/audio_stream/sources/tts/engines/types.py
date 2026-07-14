"""TTS 供应商 kind 与运行时请求模型

全局 ``TTSAudioStreamConfig`` 与模型 ``TTSpeakControllerSettings`` 均按供应商并列配置,
kind 选中激活家;连接槽经 ``getattr(tts_cfg, kind)`` 取,引擎由 ``engines`` 包注册表分发。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .fish_audio import FishAudioSpeakConfig, FishAudioSpeakRequest

# 已接入的发声供应商(控制器 kind 可选值;须与 engines.TTS_ENGINES 注册表 key 同步)
TtsProviderKind = Literal["fish_audio"]


class TtsSpeakRequest(BaseModel):
    """一次 speak 调用的运行时请求(kind + 激活供应商发声参数)。

    model/latency/speed 等全局参数不在此;由 ``TTSAudioStreamConfig`` 对应连接槽提供。
    """

    model_config = ConfigDict(extra="forbid")

    kind: TtsProviderKind = Field(default="fish_audio", description="激活的 TTS 供应商")
    fish_audio: FishAudioSpeakConfig = Field(
        default_factory=FishAudioSpeakConfig,
        description="Fish Audio 发声参数(仅 reference_id)",
    )

    def provider_request(self) -> FishAudioSpeakRequest:
        """当前 kind 对应的供应商请求模型(供引擎 synthesize)。"""

        if self.kind == "fish_audio":
            return FishAudioSpeakRequest(reference_id=self.fish_audio.reference_id)
        raise ValueError(f"未知 TTS 供应商 kind={self.kind!r}")

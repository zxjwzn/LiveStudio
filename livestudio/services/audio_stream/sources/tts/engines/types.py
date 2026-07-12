"""TTS 供应商 kind 类型

全局 ``TTSAudioStreamConfig`` 与模型 ``TTSpeakControllerSettings`` 均按供应商并列配置,
kind 选中激活家;连接槽经 ``getattr(tts_cfg, kind)`` 取,引擎由 ``engines`` 包注册表分发。
"""

from __future__ import annotations

from typing import Literal

# 已接入的发声供应商(控制器 kind 可选值;须与 engines.TTS_ENGINES 注册表 key 同步)
TtsProviderKind = Literal["fish_audio"]

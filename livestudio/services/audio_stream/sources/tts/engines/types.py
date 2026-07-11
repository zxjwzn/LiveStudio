"""TTS 供应商连接槽与 speak 选项工具

全局 ``TTSAudioStreamConfig`` 按供应商并列连接配置(GUI 全展示)。
模型 ``TTSpeakControllerSettings`` 为扁平通用字段 + kind + extra。
"""

from __future__ import annotations

from typing import Literal

from .fish_audio import FishAudioConnectionConfig

# 已接入的发声供应商(控制器 kind 可选值)
TtsProviderKind = Literal["fish_audio"]


def connection_for_kind(
    *,
    fish_audio: FishAudioConnectionConfig,
    kind: str,
) -> FishAudioConnectionConfig:
    """按 kind 取全局连接槽;未知 kind 报错。"""

    if kind == "fish_audio":
        return fish_audio
    raise RuntimeError(f"未知 TTS 供应商 kind={kind!r}(全局未配置该连接槽)")

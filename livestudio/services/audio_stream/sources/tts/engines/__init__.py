"""TTS 引擎包导出 + 供应商注册表

``TTS_ENGINES`` 是 kind 到引擎工厂的映射(新增供应商在此登记一行);
``make_engine(kind, connection, ...)`` 查表构造引擎。注册表放包入口,避免 base 与
各供应商引擎之间的循环导入。
"""

from __future__ import annotations

from collections.abc import Callable

from .base import (
    TtsAudioOutput,
    TtsEngine,
    TtsOutput,
    TtsSubtitleOutput,
)
from .fish_audio import (
    FishAudioConnectionConfig,
    FishAudioEngine,
    FishAudioSpeakConfig,
    TtsSpeakRequest,
)
from .types import TtsProviderKind

# 供应商注册表:kind -> 引擎工厂。新增供应商在此登记一行,并同步三处:
#   TtsProviderKind Literal、TTSAudioStreamConfig 连接槽、TTSpeakControllerSettings speak 配置
TTS_ENGINES: dict[str, Callable[..., TtsEngine]] = {
    "fish_audio": FishAudioEngine,
}


def make_engine(kind: str, connection: object, *, sample_rate: int, channels: int) -> TtsEngine:
    """按 kind 查注册表构造引擎;未知 kind 报错。

    connection 由调用方经 ``getattr(tts_config, kind)`` 取对应供应商的连接槽。
    """

    factory = TTS_ENGINES.get(kind)
    if factory is None:
        raise TypeError(f"未知 TTS 供应商 kind={kind!r}(未在 TTS_ENGINES 注册)")
    return factory(connection, sample_rate=sample_rate, channels=channels)


__all__ = [
    "TTS_ENGINES",
    "FishAudioConnectionConfig",
    "FishAudioEngine",
    "FishAudioSpeakConfig",
    "TtsAudioOutput",
    "TtsEngine",
    "TtsOutput",
    "TtsProviderKind",
    "TtsSpeakRequest",
    "TtsSubtitleOutput",
    "make_engine",
]

"""字幕 WebSocket 协议模型(服务端 ↔ 浏览器)"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class SubtitleMessageType(StrEnum):
    """WebSocket 消息类型"""

    BEGIN = "begin"
    SEGMENTS = "segments"
    FINISH = "finish"
    PING = "ping"
    PONG = "pong"


class _ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubtitleWireSegment(_ProtocolModel):
    """线协议中的字幕段"""

    text: str
    start: float
    end: float


class SubtitleBeginData(_ProtocolModel):
    """begin 消息负载:全文 + 当前样式/时序配置"""

    text: str
    font_path: str = ""
    font_size: int = 48
    font_color: str = "#FFFFFF"
    font_edge_color: str = "#000000"
    font_edge_width: float = 2.0
    audio_delay_ms: int = 120
    clear_delay_ms: int = 2000


class SubtitleSegmentsData(_ProtocolModel):
    """segments 消息负载"""

    segments: list[SubtitleWireSegment] = Field(default_factory=list)


class SubtitleBeginMessage(_ProtocolModel):
    type: Literal[SubtitleMessageType.BEGIN] = SubtitleMessageType.BEGIN
    data: SubtitleBeginData


class SubtitleSegmentsMessage(_ProtocolModel):
    type: Literal[SubtitleMessageType.SEGMENTS] = SubtitleMessageType.SEGMENTS
    data: SubtitleSegmentsData


class SubtitleFinishMessage(_ProtocolModel):
    type: Literal[SubtitleMessageType.FINISH] = SubtitleMessageType.FINISH


class SubtitlePongMessage(_ProtocolModel):
    type: Literal[SubtitleMessageType.PONG] = SubtitleMessageType.PONG


class SubtitlePingMessage(_ProtocolModel):
    type: Literal[SubtitleMessageType.PING] = SubtitleMessageType.PING


SubtitleServerMessage = Annotated[
    SubtitleBeginMessage | SubtitleSegmentsMessage | SubtitleFinishMessage | SubtitlePongMessage,
    Field(discriminator="type"),
]

"""字幕事件与 WebSocket 协议模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class _SubtitleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SubtitleEventKind(StrEnum):
    BEGIN = "begin"
    SEGMENTS = "segments"
    FINISH = "finish"


class SubtitleSegment(_SubtitleModel):
    """一段字幕及其在当前音频中的时间范围。"""

    text: str
    start: float
    end: float


class SubtitleEvent(_SubtitleModel):
    """字幕总线事件。"""

    kind: SubtitleEventKind
    text: str | None = None
    segments: list[SubtitleSegment] | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> SubtitleEvent:
        if self.kind is SubtitleEventKind.BEGIN:
            if self.text is None or self.segments is not None:
                raise ValueError("begin 事件必须仅包含 text")
        elif self.kind is SubtitleEventKind.SEGMENTS:
            if self.segments is None or self.text is not None:
                raise ValueError("segments 事件必须仅包含 segments")
        elif self.text is not None or self.segments is not None:
            raise ValueError("finish 事件不能包含数据")
        return self


class SubtitleBeginData(_SubtitleModel):
    text: str
    font_path: str
    font_size: int
    font_color: str
    font_edge_color: str
    font_edge_width: float
    audio_delay_ms: int
    clear_delay_ms: int


class SubtitleSegmentsData(_SubtitleModel):
    segments: list[SubtitleSegment]


class SubtitleBeginMessage(_SubtitleModel):
    type: Literal["begin"] = "begin"
    data: SubtitleBeginData


class SubtitleSegmentsMessage(_SubtitleModel):
    type: Literal["segments"] = "segments"
    data: SubtitleSegmentsData


class SubtitleFinishMessage(_SubtitleModel):
    type: Literal["finish"] = "finish"


class SubtitlePongMessage(_SubtitleModel):
    type: Literal["pong"] = "pong"


class SubtitleClientRequest(_SubtitleModel):
    """浏览器发给字幕服务的请求。"""

    type: Literal["ping"]


SubtitleServerMessage = SubtitleBeginMessage | SubtitleSegmentsMessage | SubtitleFinishMessage | SubtitlePongMessage

"""表演时间线数据模型:事件 / 草稿 / 队列 Job / 锚点相位"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    """可编排的原子事件类型(经 add_event.type 选择)。"""

    SPEAK = "speak"
    PLAY_EMOTION = "play_emotion"
    SET_NATIVE_EXPRESSION = "set_native_expression"
    CLEAR_NATIVE_EXPRESSIONS = "clear_native_expressions"
    WAIT = "wait"


class AnchorPhase(str, Enum):
    """相对锚点的相位:事件真正开始 / 真正结束。"""

    START = "start"
    END = "end"


class JobState(str, Enum):
    """队列中一份计划(Job)的生命周期。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EventStatus(str, Enum):
    """Job 内单个事件的运行态。"""

    PENDING = "pending"
    ARMED = "armed"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class StartRef(BaseModel):
    """相对锚点约束:在 anchor.phase 发生后再 delay 秒触发。

    用于事件的 start(何时开始)与可选的 end(何时强制结束/释放)。
    """

    model_config = ConfigDict(extra="forbid")

    anchor: str = Field(
        default="group",
        description='锚点:"group" 表示本 Job 的 group.start;否则为同组内事件 id',
    )
    phase: AnchorPhase = Field(default=AnchorPhase.START, description="相对锚点的 start 或 end")
    delay: float = Field(default=0.0, ge=0.0, description="相对锚点后再等待的秒数")


class TimelineEvent(BaseModel):
    """草稿或 Job 快照中的一条事件。

    start: 何时启动底层动作(默认 group.start+0)。
    end: 可选;到点后调度器强制释放/停止该动作(通用,不绑定某一 type)。
         缺省则按该 type 的自然结束(speak 播完、emotion 的 hold 结束等)。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="组内唯一 id")
    type: EventType
    params: dict[str, Any] = Field(default_factory=dict)
    start: StartRef = Field(default_factory=StartRef)
    end: StartRef | None = Field(
        default=None,
        description="可选结束约束;到点强制释放。None=自然结束",
    )


class EventRuntime(BaseModel):
    """运行期事件状态(可序列化快照)。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: EventType
    params: dict[str, Any] = Field(default_factory=dict)
    start: StartRef
    end: StartRef | None = None
    status: EventStatus = EventStatus.PENDING
    t_start: float | None = None
    t_end: float | None = None
    error: str | None = None


class JobSnapshot(BaseModel):
    """队列 Job 对外快照。"""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    state: JobState
    enqueue_delay: float = Field(default=0.0, ge=0.0)
    events: list[EventRuntime] = Field(default_factory=list)
    phase: str | None = Field(
        default=None,
        description="running 子阶段:starting_delay|playing|None",
    )
    error: str | None = None


class DraftSnapshot(BaseModel):
    """当前事件组(草稿)快照。"""

    model_config = ConfigDict(extra="forbid")

    events: list[TimelineEvent] = Field(default_factory=list)
    valid: bool = True
    errors: list[str] = Field(default_factory=list)


class QueueSnapshot(BaseModel):
    """全局队列摘要。"""

    model_config = ConfigDict(extra="forbid")

    running: JobSnapshot | None = None
    pending: list[JobSnapshot] = Field(default_factory=list)
    finished: list[JobSnapshot] = Field(default_factory=list)


def validate_event_params(event_type: EventType, params: dict[str, Any]) -> dict[str, Any]:
    """按类型校验并规范化 params;非法时抛 ValueError。"""

    if event_type is EventType.SPEAK:
        text = params.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("speak 需要非空 params.text")
        return {"text": text.strip()}

    if event_type is EventType.PLAY_EMOTION:
        emotion = params.get("emotion")
        if not isinstance(emotion, str) or not emotion.strip():
            raise ValueError("play_emotion 需要非空 params.emotion")
        out: dict[str, Any] = {"emotion": emotion.strip()}
        if "intensity" in params and params["intensity"] is not None:
            raise ValueError("play_emotion.intensity 固定为 1,不接受外部传入")
        for key in ("transition_duration", "hold_duration"):
            if key in params and params[key] is not None:
                value = float(params[key])
                if value < 0.0:
                    raise ValueError(f"play_emotion.{key} 须 >= 0")
                out[key] = value
        return out

    if event_type is EventType.SET_NATIVE_EXPRESSION:
        name = params.get("name")
        active = params.get("active")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("set_native_expression 需要非空 params.name")
        if not isinstance(active, bool):
            raise ValueError("set_native_expression 需要 bool params.active")
        return {"name": name.strip(), "active": active}

    if event_type is EventType.CLEAR_NATIVE_EXPRESSIONS:
        return {}

    if event_type is EventType.WAIT:
        seconds = params.get("seconds")
        if seconds is None:
            raise ValueError("wait 需要 params.seconds")
        value = float(seconds)
        if value < 0.0:
            raise ValueError("wait.seconds 须 >= 0")
        return {"seconds": value}

    raise ValueError(f"未知事件类型: {event_type}")


class EnqueueResult(BaseModel):
    """enqueue_draft 的返回。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    job_id: str | None = None
    state: JobState | None = None
    position: int = 0
    queue_size: int = 0
    start_delay: float = 0.0
    error: str | None = None
    message: str | None = None
    draft: DraftSnapshot | None = None
    queue: QueueSnapshot | None = None


class RemoveJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    removed: list[str] = Field(default_factory=list)
    cancelled_running: bool = False
    message: str | None = None
    queue: QueueSnapshot | None = None

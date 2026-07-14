"""Performance 调度内核数据模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    """调度器支持的事件类型。"""

    EVENT = "event"
    WAIT = "wait"


class AnchorPhase(str, Enum):
    """事件锚点相位。"""

    START = "start"
    END = "end"


class JobState(str, Enum):
    """队列任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class EventStatus(str, Enum):
    """任务内单个事件的状态。"""

    PENDING = "pending"
    ARMED = "armed"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class StartRef(BaseModel):
    """在指定锚点相位发生后延迟触发。"""

    model_config = ConfigDict(extra="forbid")

    anchor: str = Field(default="group", description='"group" 或同组事件 id')
    phase: AnchorPhase = AnchorPhase.START
    delay: float = Field(default=0.0, ge=0.0)


class TimelineEvent(BaseModel):
    """草稿或任务快照中的调度事件。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: EventType
    name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    start: StartRef = Field(default_factory=StartRef)
    end: StartRef | None = None


class EventRuntime(BaseModel):
    """运行期事件状态。"""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: EventType
    name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    start: StartRef
    end: StartRef | None = None
    status: EventStatus = EventStatus.PENDING
    t_start: float | None = None
    t_end: float | None = None
    error: str | None = None


class PerformanceEvent(BaseModel):
    """调度器发出的通用事件相位通知。"""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    event_id: str
    type: EventType
    name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    phase: AnchorPhase
    timestamp: float


class JobSnapshot(BaseModel):
    """队列任务快照。"""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    state: JobState
    enqueue_delay: float = Field(default=0.0, ge=0.0)
    events: list[EventRuntime] = Field(default_factory=list)
    phase: str | None = None
    error: str | None = None


class DraftSnapshot(BaseModel):
    """当前事件组草稿。"""

    model_config = ConfigDict(extra="forbid")

    events: list[TimelineEvent] = Field(default_factory=list)
    valid: bool = True
    errors: list[str] = Field(default_factory=list)


class QueueSnapshot(BaseModel):
    """全局队列快照。"""

    model_config = ConfigDict(extra="forbid")

    running: JobSnapshot | None = None
    pending: list[JobSnapshot] = Field(default_factory=list)
    finished: list[JobSnapshot] = Field(default_factory=list)


class EnqueueResult(BaseModel):
    """草稿入队结果。"""

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
    """删除或取消任务的结果。"""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    removed: list[str] = Field(default_factory=list)
    cancelled_running: bool = False
    message: str | None = None
    queue: QueueSnapshot | None = None

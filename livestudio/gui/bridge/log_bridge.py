"""日志桥接:loguru sink → Qt 信号

向 loguru 追加一个 sink(不移除既有 stderr sink),把日志 record 转成纯 dataclass,
经 QObject 信号以 QueuedConnection 跨线程 marshal 到 GUI(loguru enqueue 在工作线程)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from PySide6.QtCore import QObject, Signal

if TYPE_CHECKING:
    from loguru import Message


@dataclass(frozen=True, slots=True)
class LogEntry:
    """供日志页展示的一条日志(纯数据,不含 loguru 对象)"""

    level: str
    timestamp: str
    source: str
    message: str


class LogController(QObject):
    """注册 loguru sink 并把日志条目转发为 Qt 信号"""

    logEmitted = Signal(LogEntry)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sink_id: int | None = None

    def start(self, level: str = "DEBUG") -> None:
        """追加 sink(只追加不移除既有 sink,保留终端输出)"""

        if self._sink_id is not None:
            return
        self._sink_id = logger.add(
            self._sink,
            level=level.upper(),
            enqueue=True,
            backtrace=False,
            diagnose=False,
        )

    def stop(self) -> None:
        """移除本控制器注册的 sink"""

        if self._sink_id is not None:
            logger.remove(self._sink_id)
            self._sink_id = None

    def set_level(self, level: str) -> None:
        """改变接收级别:移除旧 sink 后按新级别重加"""

        self.stop()
        self.start(level)

    def _sink(self, message: Message) -> None:
        # loguru 传入的 message 带 typed .record;在工作线程调用,故只构造数据并 emit,
        # 由 QueuedConnection 把信号投递回 GUI 线程。
        record = message.record
        name = record["name"] or "?"
        entry = LogEntry(
            level=record["level"].name,
            timestamp=record["time"].strftime("%H:%M:%S.%f")[:-3],
            source=f"{name}:{record['function']}:{record['line']}",
            message=record["message"],
        )
        self.logEmitted.emit(entry)

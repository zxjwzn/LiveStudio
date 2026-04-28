"""应用日志封装。"""

from __future__ import annotations

import sys
import weakref
from dataclasses import dataclass
from threading import RLock
from typing import Final, TextIO

from loguru import logger as _logger

_DEFAULT_FORMAT: Final[str] = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>"
    " | <level>{level: <8}</level>"
    " | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
    " - <level>{message}</level>"
)
_STATUS_LINE_LOCK: Final[RLock] = RLock()
_ACTIVE_STATUS_LINES: Final[weakref.WeakSet[StatusLine]] = weakref.WeakSet()


def _clear_active_status_lines() -> None:
    with _STATUS_LINE_LOCK:
        for status_line in tuple(_ACTIVE_STATUS_LINES):
            _clear_status_line_unlocked(status_line)


def _log_sink(message: str) -> None:
    _clear_active_status_lines()
    sys.stderr.write(message)
    sys.stderr.flush()


def _finish_status_line_unlocked(status_line: StatusLine) -> None:
    if status_line.line_length <= 0:
        _ACTIVE_STATUS_LINES.discard(status_line)
        return
    status_line.stream.write("\n")
    status_line.stream.flush()
    status_line.line_length = 0
    _ACTIVE_STATUS_LINES.discard(status_line)


def _clear_status_line_unlocked(status_line: StatusLine) -> None:
    if status_line.line_length <= 0:
        _ACTIVE_STATUS_LINES.discard(status_line)
        return
    status_line.stream.write(f"\r{' ' * status_line.line_length}\r")
    status_line.stream.flush()
    status_line.line_length = 0
    _ACTIVE_STATUS_LINES.discard(status_line)


_logger.remove()
_logger.add(
    _log_sink,
    format=_DEFAULT_FORMAT,
    level="DEBUG",
    colorize=True,
    enqueue=True,
    backtrace=False,
    diagnose=False,
)

logger = _logger.bind(app="livestudio")


@dataclass(eq=False)
class StatusLine:
    """在同一终端行刷新状态文本。"""

    stream: TextIO = sys.stderr
    line_length: int = 0

    def update(self, message: str) -> None:
        """原地刷新状态文本。"""

        with _STATUS_LINE_LOCK:
            padding = " " * max(0, self.line_length - len(message))
            self.stream.write(f"\r{message}{padding}")
            self.stream.flush()
            self.line_length = len(message)
            _ACTIVE_STATUS_LINES.add(self)

    def finish(self) -> None:
        """结束状态行并换行。"""

        with _STATUS_LINE_LOCK:
            _finish_status_line_unlocked(self)


def configure_logging(*, level: str = "DEBUG") -> None:
    """重新配置全局日志输出。"""

    _logger.remove()
    _logger.add(
        _log_sink,
        format=_DEFAULT_FORMAT,
        level=level.upper(),
        colorize=True,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

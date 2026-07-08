"""应用日志封装"""

import os
import sys
import weakref
from dataclasses import dataclass, field
from threading import RLock
from typing import Final, TextIO

from loguru import logger as _logger

from livestudio.utils.constants import DEFAULT_LOG_FORMAT

# 默认日志级别取自环境变量，缺省 INFO（避免导入即固定为 DEBUG 造成生产环境过于冗长）
_DEFAULT_LEVEL: Final[str] = os.environ.get("LIVESTUDIO_LOG_LEVEL", "INFO")
_STATUS_LINE_LOCK: Final[RLock] = RLock()
_ACTIVE_STATUS_LINES: Final[weakref.WeakSet["StatusLine"]] = weakref.WeakSet()


def _clear_active_status_lines() -> None:
    with _STATUS_LINE_LOCK:
        for status_line in tuple(_ACTIVE_STATUS_LINES):
            _clear_status_line_unlocked(status_line)


def _log_sink(message: str) -> None:
    _clear_active_status_lines()
    sys.stderr.write(message)
    sys.stderr.flush()


def _finish_status_line_unlocked(status_line: "StatusLine") -> None:
    if status_line.line_length <= 0:
        _ACTIVE_STATUS_LINES.discard(status_line)
        return
    status_line.stream.write("\n")
    status_line.stream.flush()
    status_line.line_length = 0
    _ACTIVE_STATUS_LINES.discard(status_line)


def _clear_status_line_unlocked(status_line: "StatusLine") -> None:
    if status_line.line_length <= 0:
        _ACTIVE_STATUS_LINES.discard(status_line)
        return
    status_line.stream.write(f"\r{' ' * status_line.line_length}\r")
    status_line.stream.flush()
    status_line.line_length = 0
    _ACTIVE_STATUS_LINES.discard(status_line)


_configured: bool = False


def _install_log_sink(level: str) -> None:
    global _configured
    _logger.remove()
    _logger.add(
        _log_sink,
        format=DEFAULT_LOG_FORMAT,
        level=level.upper(),
        colorize=True,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )
    _configured = True


def _ensure_configured() -> None:
    """惰性装配日志 sink：仅在尚未配置时装一次，幂等。

    替代「导入即无条件 _logger.remove() 抢占全局 sink」的硬副作用——重复 import
    或测试反复触发都不会重复抢占；宿主或测试可通过 configure_logging() 显式重配。
    """

    if not _configured:
        _install_log_sink(_DEFAULT_LEVEL)


# 保留「import 即可用」的体验，但经幂等守卫，不再每次都抢占全局 sink
_ensure_configured()

logger = _logger.bind(app="livestudio")


@dataclass(eq=False)
class StatusLine:
    """在同一终端行刷新状态文本"""

    # 用 default_factory 延迟到实例化时取 sys.stderr，支持运行期重定向 stderr 后新实例写新流
    stream: TextIO = field(default_factory=lambda: sys.stderr)
    line_length: int = 0

    def update(self, message: str) -> None:
        """原地刷新状态文本"""

        with _STATUS_LINE_LOCK:
            padding = " " * max(0, self.line_length - len(message))
            self.stream.write(f"\r{message}{padding}")
            self.stream.flush()
            self.line_length = len(message)
            _ACTIVE_STATUS_LINES.add(self)

    def finish(self) -> None:
        """结束状态行并换行"""

        with _STATUS_LINE_LOCK:
            _finish_status_line_unlocked(self)


def configure_logging(*, level: str | None = None) -> None:
    """重新配置全局日志输出；level 省略时取环境变量 LIVESTUDIO_LOG_LEVEL（缺省 INFO）"""

    _install_log_sink(level or _DEFAULT_LEVEL)

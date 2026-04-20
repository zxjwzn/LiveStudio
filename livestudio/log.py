"""应用日志封装。"""

from __future__ import annotations

import sys
from typing import Final

from loguru import logger as _logger

_DEFAULT_FORMAT: Final[str] = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>"
    " | <level>{level: <8}</level>"
    " | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
    " - <level>{message}</level>"
)

_logger.remove()
_logger.add(
    sys.stderr,
    format=_DEFAULT_FORMAT,
    level="DEBUG",
    colorize=True,
    enqueue=True,
    backtrace=False,
    diagnose=False,
)

logger = _logger.bind(app="livestudio")


def configure_logging(*, level: str = "DEBUG") -> None:
    """重新配置全局日志输出。"""

    _logger.remove()
    _logger.add(
        sys.stderr,
        format=_DEFAULT_FORMAT,
        level=level.upper(),
        colorize=True,
        enqueue=True,
        backtrace=False,
        diagnose=False,
    )

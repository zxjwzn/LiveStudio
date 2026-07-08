"""工具模块常量"""

from __future__ import annotations

import math
from typing import Final

HALF_PI: Final[float] = math.pi / 2
BACK_C1: Final[float] = 1.70158
BACK_C2: Final[float] = BACK_C1 * 1.525
BACK_C3: Final[float] = BACK_C1 + 1
ELASTIC_C4: Final[float] = (2 * math.pi) / 3
ELASTIC_C5: Final[float] = (2 * math.pi) / 4.5
BOUNCE_N1: Final[float] = 7.5625
BOUNCE_D1: Final[float] = 2.75

DEFAULT_LOG_FORMAT: Final[str] = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>"
    " | <level>{level: <8}</level>"
    " | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>"
    " - <level>{message}</level>"
)

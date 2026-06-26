"""通知去重节流

把日志里高频重复的 WARNING/ERROR 收敛成稀疏通知:同一 (level, message) 在时间窗内只放行一次,
避免短时间内同一告警刷屏。纯逻辑、无 Qt 依赖,由调用方据 should_emit 的返回决定是否真正弹 InfoBar。
"""

from __future__ import annotations

import time


class ThrottledNotifier:
    """按 (级别, 消息) 去重的时间窗节流器"""

    def __init__(self, window_seconds: float = 5.0) -> None:
        self._window = window_seconds
        self._last_emit: dict[tuple[str, str], float] = {}

    def should_emit(self, level: str, message: str) -> bool:
        """该 (level, message) 是否应放行通知:窗口内重复则压制。

        放行时记录本次时间戳;顺带惰性清理已过期的 key,避免长期运行时表无限增长。
        """

        now = time.monotonic()
        self._prune(now)
        key = (level, message)
        last = self._last_emit.get(key)
        if last is not None and now - last < self._window:
            return False
        self._last_emit[key] = now
        return True

    def _prune(self, now: float) -> None:
        expired = [key for key, ts in self._last_emit.items() if now - ts >= self._window]
        for key in expired:
            del self._last_emit[key]

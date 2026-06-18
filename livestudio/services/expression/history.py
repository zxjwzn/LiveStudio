"""历史签名队列，提供重复惩罚计算"""

from __future__ import annotations

from collections import deque

from livestudio.services.expression.models import EmotionKind, ExpressionSignature


class ExpressionHistory:
    def __init__(self, capacity: int = 20) -> None:
        self._capacity = capacity
        self._queue: deque[ExpressionSignature] = deque()

    def recent(self) -> list[ExpressionSignature]:
        """返回所有历史签名，最新的在前"""
        return list(self._queue)

    def penalty(
        self, candidate: ExpressionSignature, history_avoidance: float
    ) -> float:
        """计算候选组合与历史记录的相似度惩罚分"""
        if not self._queue or history_avoidance <= 0.0:
            return 0.0

        max_weighted = 0.0
        capacity = self._capacity or len(self._queue)

        for index, hist in enumerate(self._queue):
            union = candidate.unit_ids | hist.unit_ids
            if not union:
                unit_jaccard = 1.0
            else:
                unit_jaccard = len(candidate.unit_ids & hist.unit_ids) / len(union)

            emotion_match = 1.0 if candidate.emotion == hist.emotion else 0.0
            similarity = unit_jaccard * 0.65 + emotion_match * 0.35
            recency_weight = 1.0 - (index / capacity)
            weighted = similarity * recency_weight
            if weighted > max_weighted:
                max_weighted = weighted

        return max_weighted * history_avoidance

    def record(self, sig: ExpressionSignature) -> None:
        """记录一次真实选择，最新的插入队头，超出容量时丢弃队尾"""
        self._queue.appendleft(sig)
        while len(self._queue) > self._capacity:
            self._queue.pop()

    def snapshot(self) -> list[ExpressionSignature]:
        """返回当前状态快照（用于 preview 恢复）"""
        return list(self._queue)

    def restore(self, snapshot: list[ExpressionSignature]) -> None:
        self._queue = deque(snapshot)

    @property
    def recent_unit_ids(self) -> frozenset[str]:
        return frozenset(uid for sig in self._queue for uid in sig.unit_ids)

    def __len__(self) -> int:
        return len(self._queue)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EmotionKind):
            return NotImplemented
        return NotImplemented

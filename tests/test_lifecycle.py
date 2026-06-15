"""测试服务级生命周期链路"""

from __future__ import annotations

import pytest

from livestudio.services.lifecycle import AsyncServiceLifecycleMixin


class _LifecycleService(AsyncServiceLifecycleMixin):
    def __init__(self, *, fail_start: bool = False) -> None:
        self.fail_start = fail_start
        self.calls: list[str] = []

    async def initialize(self) -> None:
        self.calls.append("initialize")

    async def start(self) -> None:
        self.calls.append("start")
        if self.fail_start:
            raise RuntimeError("start failed")

    async def stop(self) -> None:
        self.calls.append("stop")


async def test_lifecycle_context_runs_full_start_stop_flow() -> None:
    service = _LifecycleService()

    async with service as entered:
        assert entered is service

    assert service.calls == ["initialize", "start", "stop"]


async def test_lifecycle_context_stops_after_failed_start() -> None:
    service = _LifecycleService(fail_start=True)

    with pytest.raises(RuntimeError, match="start failed"):
        async with service:
            pass

    assert service.calls == ["initialize", "start", "stop"]

"""共享 pytest 测试准备项"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def event_loop_policy():
    """让 asyncio 使用默认策略，Windows 上 selector 已经够用"""

    return asyncio.DefaultEventLoopPolicy()

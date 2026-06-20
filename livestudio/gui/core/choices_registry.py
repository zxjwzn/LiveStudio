"""动态下拉选项数据源注册表。

配置编辑器里的 enum 字段，选项可能不是静态的（如麦克风设备列表需要
``await mic.list_input_devices()`` 动态获取，且会随设备插拔变化）。静态
``choices`` 装不下这种逻辑，因此把"选项数据源"抽象成 provider：

- ConfigFieldVM 只携带一个 ``choices_source`` 字符串 key（纯数据、可序列化）。
- 复杂的异步获取逻辑收敛在 provider 函数里，注册到本表。
- 编辑器渲染 enum 字段时按 key 查表、异步拉取，处理 loading/失败/刷新。

provider 必须是 async 无参可调用，返回 ``list[ChoiceVM]``。
"""

from __future__ import annotations

from typing import Awaitable, Callable

from .view_models import ChoiceVM

ChoicesProvider = Callable[[], Awaitable[list[ChoiceVM]]]


class ChoicesRegistry:
    """按 key 注册/解析动态下拉选项 provider。"""

    def __init__(self) -> None:
        self._providers: dict[str, ChoicesProvider] = {}

    def register(self, source: str, provider: ChoicesProvider) -> None:
        """注册一个选项数据源；同 key 重复注册将覆盖。"""

        self._providers[source] = provider

    def has(self, source: str) -> bool:
        """是否存在该数据源。"""

        return source in self._providers

    async def resolve(self, source: str) -> list[ChoiceVM]:
        """拉取指定数据源的选项；未注册返回空列表。"""

        provider = self._providers.get(source)
        if provider is None:
            return []
        return await provider()

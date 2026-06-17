"""保存界面当前状态的地方。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PageId(StrEnum):
    """每个页面的名字。"""

    MONITOR = "monitor"
    PLATFORM = "platform"
    AUDIO = "audio"
    EXPRESSION = "expression"
    CONTROLLERS = "controllers"


@dataclass(slots=True)
class PageState:
    """某一个页面自己的临时数据。"""

    values: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GUIState:
    """所有页面都能读取和修改的界面状态。"""

    current_page: PageId = PageId.MONITOR
    status_message: str = "就绪"
    pages: dict[PageId, PageState] = field(
        default_factory=lambda: {page_id: PageState() for page_id in PageId},
    )

    def page_state(self, page_id: PageId) -> PageState:
        return self.pages[page_id]

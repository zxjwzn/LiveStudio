"""动画模板常量"""

from typing import Final

from livestudio.services.semantic_actions import DEFAULT_SEMANTIC_ACTION_SPECS

SEMANTIC_ACTION_NAMES: Final[set[str]] = {spec.id.value for spec in DEFAULT_SEMANTIC_ACTION_SPECS}

TEMPLATE_PRIORITY: Final[int] = 50

"""配置编辑器的字段描述数据结构

把 Pydantic 的 FieldInfo 内省结果归一成 GUI 可直接消费的 FieldSpec,以及类型类别
FieldKind。工厂据此分派编辑器,无需在各处重复解析类型。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from qfluentwidgets import FluentIcon

# 注入候选项:显示名 + 写回值(如音频设备名/索引)
ChoiceItem = tuple[str, Any]
ChoicesProvider = Callable[[], list[ChoiceItem]]


def resolve_icon(icon: FluentIcon | None) -> FluentIcon:
    """字段图标回退:无显式图标时用透明占位,保证 SettingCard 左侧留白对齐"""

    return icon or FluentIcon.TRANSPARENT


class FieldKind(Enum):
    """字段类型类别(决定用哪个编辑器)"""

    BOOL = auto()
    INT = auto()
    FLOAT = auto()
    STR = auto()
    PATH = auto()
    CHOICE = auto()  # Literal / Enum / 外部注入候选
    MODEL = auto()  # 嵌套 BaseModel
    LIST = auto()
    DICT = auto()
    OPTIONAL = auto()  # X | None
    UNION = auto()  # 多成员联合(非单纯 Optional)
    TAGGED_UNION = auto()  # 带 discriminator 的多 BaseModel 判别联合(如 ExpressionRule)
    READONLY = auto()  # exotic 子树兜底:只读


@dataclass
class FieldSpec:
    """单个字段的归一化描述"""

    name: str
    label: str
    description: str
    kind: FieldKind
    annotation: Any
    # 标量约束
    minimum: float | None = None
    maximum: float | None = None
    # 选择类:候选字面量(Literal/Enum 成员值)
    choices: list[Any] = field(default_factory=list)
    # 外部注入候选(优先于 choices)
    choices_provider: ChoicesProvider | None = None
    # 容器/嵌套:元素或子模型类型信息由工厂按 annotation 再解析
    inner_annotations: tuple[Any, ...] = ()
    # 嵌套模型类型(MODEL)
    model_type: type | None = None
    # 可空(OPTIONAL/UNION 内是否含 None)
    optional: bool = False
    readonly: bool = False
    # 判别联合(TAGGED_UNION):判别字段名 + (判别值 → 成员 BaseModel 类型) 有序映射
    discriminator: str | None = None
    union_members: tuple[tuple[str, type], ...] = ()
    # 左侧图标(来自 json_schema_extra["icon"]);None 时由编辑器回退为占位图标
    icon: FluentIcon | None = None
    # bare 模式:被容器(Optional/Union/List)复用时只渲染控件、不画 SettingCard 外壳
    bare: bool = False

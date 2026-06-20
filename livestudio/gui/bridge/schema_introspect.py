"""Pydantic 模型 → ConfigSectionVM 反射。

把一个 Pydantic 模型实例自动转换为通用配置编辑器吃的 ConfigFieldVM 列表：
- 数据类型由 annotation 推断（bool/int/float/str/enum）。
- min/max 由 field 的 Ge/Le/Gt/Lt 约束元数据提取。
- 默认值、当前值、说明（description）全自动。
- Literal[...] 自动转成 enum 的静态 choices。

字段级的人工补充（中文短标题、换控件、绑动态下拉源）走 overrides 覆盖层：
90% 字段零配置（label 缺省用 description），只有想定制的少数字段写一行 override。

依赖约束：本模块属 bridge 层，允许 import pydantic 与后端模型。
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass
from enum import Enum
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from ..core.view_models import ChoiceVM, ConfigFieldVM, ConfigSectionVM, ValueType


@dataclass(frozen=True)
class FieldOverride:
    """对单个字段的人工覆盖（schema 推不出来的部分）。"""

    label: str | None = None  # 中文短标题；缺省用 description 或字段名
    widget: str | None = None  # 换控件：slider / spinbox / dropdown / 自定义 key
    choices_source: str | None = None  # 绑动态下拉源（查 ChoicesRegistry）
    help: str | None = None  # 覆盖说明文案；缺省用 description
    hidden: bool = False  # 不在编辑器里展示该字段
    min: float | None = None  # 覆盖数值下限
    max: float | None = None  # 覆盖数值上限
    step: float | None = None  # 滑块/旋钮步长


def _unwrap_optional(annotation: Any) -> Any:
    """把 Optional[X] / Union[X, None] 还原成 X；非可选原样返回。"""

    # 同时认 typing.Union[X, None] 与 PEP 604 的 X | None（types.UnionType）
    if get_origin(annotation) in (typing.Union, types.UnionType):
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _literal_choices(annotation: Any) -> tuple[ChoiceVM, ...]:
    """Literal[...] -> 静态 choices；非 Literal 返回空。"""

    if get_origin(annotation) is typing.Literal:
        return tuple(ChoiceVM(value=arg, label=str(arg)) for arg in get_args(annotation))
    return ()


def _enum_choices(annotation: Any) -> tuple[ChoiceVM, ...]:
    """Enum 子类 -> 静态 choices（用成员 value）。"""

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return tuple(ChoiceVM(value=member.value, label=str(member.value)) for member in annotation)
    return ()


def _infer_value_type(annotation: Any) -> tuple[ValueType, tuple[ChoiceVM, ...]]:
    """从 annotation 推断 value_type 与（若是枚举）静态 choices。"""

    base = _unwrap_optional(annotation)

    literal = _literal_choices(base)
    if literal:
        return "enum", literal
    enum_choices = _enum_choices(base)
    if enum_choices:
        return "enum", enum_choices

    if base is bool:
        return "bool", ()
    if base is int:
        return "int", ()
    if base is float:
        return "float", ()
    if base is str:
        return "str", ()
    if isinstance(base, type) and issubclass(base, BaseModel):
        return "group", ()
    # 兜底当作字符串编辑
    return "str", ()


def _merge_override(info: FieldInfo, code_override: FieldOverride) -> FieldOverride:
    """合并字段的 GUI 元数据：Pydantic 模型的 json_schema_extra(gui_* 键)作为基线，
    代码侧 FieldOverride 显式设置的项优先覆盖。

    模型侧支持的键：gui_label / gui_widget / gui_choices_source / gui_help /
    gui_hidden / gui_min / gui_max / gui_step。这样字段的展示元数据可直接写在
    配置模型里（贴近数据定义），无需在 GUI 覆盖表里重复声明。
    """

    extra = info.json_schema_extra
    if not isinstance(extra, dict):
        return code_override

    def _str(key: str) -> str | None:
        value = extra.get(key)
        return value if isinstance(value, str) else None

    def _num(key: str) -> float | None:
        value = extra.get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    return FieldOverride(
        label=code_override.label if code_override.label is not None else _str("gui_label"),
        widget=code_override.widget if code_override.widget is not None else _str("gui_widget"),
        choices_source=(
            code_override.choices_source if code_override.choices_source is not None else _str("gui_choices_source")
        ),
        help=code_override.help if code_override.help is not None else _str("gui_help"),
        hidden=code_override.hidden or bool(extra.get("gui_hidden", False)),
        min=code_override.min if code_override.min is not None else _num("gui_min"),
        max=code_override.max if code_override.max is not None else _num("gui_max"),
        step=code_override.step if code_override.step is not None else _num("gui_step"),
    )


def _extract_bounds(info: FieldInfo) -> tuple[float | None, float | None]:
    """从字段约束元数据提取数值上下限（Ge/Gt -> min，Le/Lt -> max）。"""

    minimum: float | None = None
    maximum: float | None = None
    for meta in info.metadata:
        if (ge := getattr(meta, "ge", None)) is not None:
            minimum = float(ge)
        if (gt := getattr(meta, "gt", None)) is not None:
            minimum = float(gt)
        if (le := getattr(meta, "le", None)) is not None:
            maximum = float(le)
        if (lt := getattr(meta, "lt", None)) is not None:
            maximum = float(lt)
    return minimum, maximum


def _field_default(info: FieldInfo) -> Any:
    """取字段默认值；无默认（PydanticUndefined）返回 None。"""

    default = info.default
    # PydanticUndefined 不是公开类型，用 repr 兜底判断
    if default is None or repr(default) == "PydanticUndefined":
        return None
    return default


def introspect_model(
    model: BaseModel,
    *,
    section_id: str,
    title: str,
    overrides: dict[str, FieldOverride] | None = None,
    path_prefix: str = "",
) -> ConfigSectionVM:
    """把一个 Pydantic 模型实例反射成 ConfigSectionVM。"""

    overrides = overrides or {}
    fields = _introspect_fields(model, overrides=overrides, path_prefix=path_prefix)
    return ConfigSectionVM(id=section_id, title=title, fields=tuple(fields))


def _introspect_fields(
    model: BaseModel,
    *,
    overrides: dict[str, FieldOverride],
    path_prefix: str,
) -> list[ConfigFieldVM]:
    """反射模型的字段列表（嵌套 BaseModel 递归成 group）。"""

    result: list[ConfigFieldVM] = []
    for name, info in type(model).model_fields.items():
        # 模型侧 json_schema_extra(gui_*) 为基线，代码侧 overrides 优先覆盖
        override = _merge_override(info, overrides.get(name, FieldOverride()))
        if override.hidden:
            continue

        path = f"{path_prefix}.{name}" if path_prefix else name
        value = getattr(model, name, None)
        value_type, choices = _infer_value_type(info.annotation)
        label = override.label or name
        help_text = override.help if override.help is not None else (info.description or "")

        if value_type == "group" and isinstance(value, BaseModel):
            sub_fields = _introspect_fields(value, overrides=overrides, path_prefix=path)
            result.append(
                ConfigFieldVM(
                    path=path,
                    label=label,
                    value_type="group",
                    fields=tuple(sub_fields),
                    help=help_text,
                )
            )
            continue

        bound_min, bound_max = _extract_bounds(info)
        widget = override.widget or "auto"
        # 绑了动态源则强制走 dropdown，且清掉静态 choices
        choices_source = override.choices_source or ""
        if choices_source:
            value_type = "enum"
            choices = ()
            if widget == "auto":
                widget = "dropdown"

        result.append(
            ConfigFieldVM(
                path=path,
                label=label,
                value_type=value_type,
                widget=widget,
                value=value,
                default=_field_default(info),
                choices=choices,
                choices_source=choices_source,
                min=override.min if override.min is not None else bound_min,
                max=override.max if override.max is not None else bound_max,
                step=override.step,
                help=help_text,
            )
        )
    return result

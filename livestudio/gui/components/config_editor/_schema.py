"""Pydantic 模型的 typed 内省

把 model_fields 的 FieldInfo 解析成 FieldSpec。全程只用 typed API
(model_fields / FieldInfo / typing.get_origin/get_args / issubclass),不用 getattr/setattr,
不靠字段名硬编码。判别联合(带 discriminator)、set/frozenset[标量]、StrEnum/IntEnum 键 dict
均可结构化编辑;仅真正不安全的子树(无判别的多模型裸联合、模型集合等)兜底为只读。
"""

from __future__ import annotations

import enum
import types
import typing
from collections.abc import Mapping
from typing import Any, Literal, Union

import annotated_types as at
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from qfluentwidgets import FluentIcon

from livestudio.utils.log import logger

from ._schema_types import ChoicesProvider, FieldKind, FieldSpec
from .constants import NONE_TYPE


def _unwrap_annotated(annotation: Any) -> Any:
    """剥掉 typing.Annotated 外壳,返回被标注的真实类型(无 Annotated 时原样返回)"""

    if typing.get_origin(annotation) is typing.Annotated:
        return typing.get_args(annotation)[0]
    return annotation


def _is_scalar_key(annotation: Any) -> bool:
    """dict 键 / set 元素是否为可双向用 str/int 表示的标量(含 StrEnum/IntEnum 子类)"""

    if annotation in (str, int):
        return True
    return isinstance(annotation, type) and issubclass(annotation, enum.Enum) and issubclass(annotation, (str, int))


def is_exclude(info: FieldInfo) -> bool:
    """字段是否被 exclude(不入快照,GUI 隐藏)"""

    return info.exclude is True


def _extra_flag(info: FieldInfo, key: str) -> bool:
    extra = info.json_schema_extra
    return isinstance(extra, Mapping) and bool(extra.get(key))


def _extra_str(info: FieldInfo, key: str) -> str | None:
    """读取 json_schema_extra 中字符串型键(如 "filter");非字符串/无 extra 返回 None"""

    extra = info.json_schema_extra
    if isinstance(extra, Mapping):
        value = extra.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _icon_by_name(name: object) -> FluentIcon | None:
    """按字符串名查 FluentIcon(不用 getattr);非字符串返回 None,未知名告警并回退 None"""

    if not isinstance(name, str):
        return None
    icon = FluentIcon.__members__.get(name)
    if icon is None:
        logger.warning("未知 FluentIcon 名称 {!r}(图标回退为占位)", name)
    return icon


def _icon_of(info: FieldInfo) -> FluentIcon | None:
    """读取字段级 json_schema_extra["icon"] 并按名查 FluentIcon;无则 None"""

    extra = info.json_schema_extra
    if not isinstance(extra, Mapping):
        return None
    return _icon_by_name(extra.get("icon"))


def _model_icon_of(model_type: type[BaseModel]) -> FluentIcon | None:
    """读取模型级 json_schema_extra["icon"] 并按名查 FluentIcon;无则 None。

    在 model_config = ConfigDict(json_schema_extra={"icon": "名称"}) 上标注。
    用作字段未显式标 icon 时的回退:嵌套模型字段与 list 元素模型(经合成 FieldInfo
    渲染、永远拿不到字段级 icon)都能据此显示模型自带的图标。
    """

    extra = model_type.model_config.get("json_schema_extra")
    if not isinstance(extra, Mapping):
        return None
    return _icon_by_name(extra.get("icon"))


def is_hidden(info: FieldInfo) -> bool:
    """exclude 或 json_schema_extra.hidden 的字段在 GUI 隐藏"""

    return is_exclude(info) or _extra_flag(info, "hidden")


def _widget_hint(info: FieldInfo) -> str | None:
    """读取 json_schema_extra.widget(如 "path"),无则 None"""

    extra = info.json_schema_extra
    if isinstance(extra, Mapping):
        widget = extra.get("widget")
        if isinstance(widget, str):
            return widget
    return None


def _label_of(name: str, info: FieldInfo) -> str:
    extra = info.json_schema_extra
    if isinstance(extra, Mapping):
        label = extra.get("label")
        if isinstance(label, str) and label:
            return label
    return name.replace("_", " ").strip().capitalize()


def title_field_of(model_type: type[BaseModel]) -> str | None:
    """读取模型级 json_schema_extra["title_field"]:容器卡用该字段的「值」作标题。

    在 model_config = ConfigDict(json_schema_extra={"title_field": "字段名"}) 上标注。
    用于列表元素等场景:让卡片标题显示元素内某字段的值(如 action 名),而非 [0] 索引。
    返回字段名;未标注或字段不存在则 None。
    """

    extra = model_type.model_config.get("json_schema_extra")
    if not isinstance(extra, Mapping):
        return None
    field = extra.get("title_field")
    if isinstance(field, str) and field in model_type.model_fields:
        return field
    return None



def _as_number(value: object) -> float | None:
    """把 annotated_types 约束里的界值收敛为 float;非数值返回 None。

    annotated_types 把界值标注为 SupportsGe/Gt 等协议而非具体数字,这里在运行时
    按真实数值类型(int/float)收敛,避免对协议类型做 float() 而触发类型错误。
    """

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _bounds(info: FieldInfo) -> tuple[float | None, float | None]:
    minimum: float | None = None
    maximum: float | None = None
    for item in info.metadata:
        if isinstance(item, at.Ge):
            minimum = _as_number(item.ge)
        elif isinstance(item, at.Gt):
            minimum = _as_number(item.gt)
        elif isinstance(item, at.Le):
            maximum = _as_number(item.le)
        elif isinstance(item, at.Lt):
            maximum = _as_number(item.lt)
    return minimum, maximum


def _is_union(annotation: Any) -> bool:
    origin = typing.get_origin(annotation)
    return origin is Union or origin is types.UnionType


def _non_none_args(annotation: Any) -> tuple[Any, ...]:
    return tuple(arg for arg in typing.get_args(annotation) if arg is not NONE_TYPE)


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _discriminator_of(annotation: Any) -> str | None:
    """取 Annotated 判别联合的判别字段名(如 ExpressionRule 的 "kind");非判别联合返回 None。

    pydantic 把判别写在 Annotated 元数据的 FieldInfo.discriminator 上。
    """

    if typing.get_origin(annotation) is not typing.Annotated:
        return None
    for meta in typing.get_args(annotation)[1:]:
        if isinstance(meta, FieldInfo) and isinstance(meta.discriminator, str):
            return meta.discriminator
    return None


def _literal_value_of(model: type[BaseModel], field_name: str) -> str | None:
    """取某 BaseModel 判别字段的 Literal 值(如 MutualExclusionRule.kind → "mutual_exclusion")"""

    info = model.model_fields.get(field_name)
    if info is None:
        return None
    if typing.get_origin(info.annotation) is Literal:
        args = typing.get_args(info.annotation)
        if len(args) == 1 and isinstance(args[0], str):
            return args[0]
    return None


def _tagged_union_members(annotation: Any) -> tuple[str, tuple[tuple[str, type], ...]] | None:
    """解析带 discriminator 的多 BaseModel 联合。

    返回 (判别字段名, ((判别值, 成员类型), ...));不是判别联合返回 None。
    """

    discriminator = _discriminator_of(annotation)
    if discriminator is None:
        return None
    inner = _unwrap_annotated(annotation)
    if not _is_union(inner):
        return None
    members: list[tuple[str, type]] = []
    for member in _non_none_args(inner):
        if not _is_model(member):
            return None
        value = _literal_value_of(member, discriminator)
        if value is None:
            return None
        members.append((value, member))
    if len(members) < 2:
        return None
    return discriminator, tuple(members)


def _is_enum(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, enum.Enum)


def _is_exotic(annotation: Any) -> bool:
    """递归判断类型树是否含 v1 不安全编辑的结构。

    命中任一即视为 exotic(只读):set/frozenset[非标量]、非标量键 dict、
    无判别的多 BaseModel 裸联合。判别联合(带 discriminator,如 ExpressionRule)与
    set/frozenset[标量]、StrEnum/IntEnum 键 dict 现在均可结构化编辑,不再 exotic。
    """

    # 判别联合(带 discriminator)可结构化编辑 —— 在剥 Annotated 前先判,否则会丢失 discriminator
    if _tagged_union_members(annotation) is not None:
        return False

    annotation = _unwrap_annotated(annotation)
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    if origin in (set, frozenset):
        # 标量集合(frozenset[str] / frozenset[EmotionKind])可当 list 编辑;元素为模型/嵌套容器才 exotic
        if not args:
            return False
        return not _is_scalar_key(args[0])

    if origin in (dict, Mapping):
        if not args:
            return False
        if not _is_scalar_key(args[0]):
            return True
        return any(_is_exotic(arg) for arg in args[1:])

    if _is_union(annotation):
        members = _non_none_args(annotation)
        # 无判别的多 BaseModel 裸联合仍 exotic(本项目无此情况);判别联合已在上方放行
        if len([m for m in members if _is_model(m)]) >= 2:
            return True
        return any(_is_exotic(m) for m in members)

    if origin in (list, tuple):
        return any(_is_exotic(arg) for arg in args)

    # BaseModel 永不整体 exotic:粒度交给 ModelEditor 逐字段重判,
    # 个别 exotic 子字段(如判别联合)单独退化为只读,不拖累整个模型不可编辑。
    return False


def _classify(annotation: Any) -> FieldKind:
    """把类型注解归类到 FieldKind(不含 exotic 判定,exotic 由调用方先行处理)"""

    # 判别联合在剥 Annotated 前先判(discriminator 在 Annotated 元数据上)
    if _tagged_union_members(annotation) is not None:
        return FieldKind.TAGGED_UNION

    annotation = _unwrap_annotated(annotation)
    if annotation is bool:
        return FieldKind.BOOL
    if annotation is int:
        return FieldKind.INT
    if annotation is float:
        return FieldKind.FLOAT
    if annotation is str:
        return FieldKind.STR
    if typing.get_origin(annotation) is Literal:
        return FieldKind.CHOICE
    if _is_enum(annotation):
        return FieldKind.CHOICE
    if _is_model(annotation):
        return FieldKind.MODEL

    origin = typing.get_origin(annotation)
    # set/frozenset[标量] 当作元素列表编辑:产出 list,json 模式下 pydantic 收回 frozenset(自动去重)
    if origin in (list, tuple, set, frozenset):
        return FieldKind.LIST
    if origin in (dict, Mapping):
        return FieldKind.DICT

    if _is_union(annotation):
        members = _non_none_args(annotation)
        has_none = len(members) != len(typing.get_args(annotation))
        if has_none and len(members) == 1:
            return FieldKind.OPTIONAL
        return FieldKind.UNION

    return FieldKind.STR


def build_field_spec(
    name: str,
    info: FieldInfo,
    *,
    choices_provider: ChoicesProvider | None = None,
) -> FieldSpec:
    """把单个 FieldInfo 解析成 FieldSpec(typed,不用 getattr/setattr)"""

    annotation = info.annotation
    label = _label_of(name, info)
    description = info.description or ""
    readonly = _extra_flag(info, "readonly")
    minimum, maximum = _bounds(info)
    icon = _icon_of(info)

    # 注入候选优先:无论底层类型为何,命中即作为选择控件
    if choices_provider is not None:
        return FieldSpec(
            name=name,
            label=label,
            description=description,
            kind=FieldKind.CHOICE,
            annotation=annotation,
            choices_provider=choices_provider,
            readonly=readonly,
            icon=icon,
            optional=_is_union(annotation) and len(_non_none_args(annotation)) != len(typing.get_args(annotation)),
        )

    if _is_exotic(annotation):
        return FieldSpec(
            name=name,
            label=label,
            description=description,
            kind=FieldKind.READONLY,
            annotation=annotation,
            readonly=True,
            icon=icon,
        )

    # 路径控件:str 字段标 json_schema_extra={"widget": "path"|"file"} 时用 浏览 控件
    # "path"=目录选择(默认),"file"=文件选择(可用 "filter" 给文件对话框名称过滤器)
    widget = _widget_hint(info)
    if widget in ("path", "file") and annotation is str:
        return FieldSpec(
            name=name,
            label=label,
            description=description,
            kind=FieldKind.PATH,
            annotation=annotation,
            readonly=readonly,
            icon=icon,
            path_mode="file" if widget == "file" else "dir",
            path_filter=_extra_str(info, "filter"),
        )

    # 调色板控件:str 字段标 json_schema_extra={"widget": "color"} 时用调色板按钮
    if widget == "color" and annotation is str:
        return FieldSpec(
            name=name,
            label=label,
            description=description,
            kind=FieldKind.COLOR,
            annotation=annotation,
            readonly=readonly,
            icon=icon,
        )

    kind = _classify(annotation)
    # 字段未显式标 icon 且为嵌套模型时,回退到该模型 model_config 上的 icon。
    # list/dict 元素模型经合成 FieldInfo 渲染、永远无字段级 icon,靠这条拿到模型自带图标。
    if icon is None and kind is FieldKind.MODEL:
        icon = _model_icon_of(_unwrap_annotated(annotation))
    spec = FieldSpec(
        name=name,
        label=label,
        description=description,
        kind=kind,
        annotation=annotation,
        minimum=minimum,
        maximum=maximum,
        readonly=readonly,
        icon=icon,
    )

    if kind is FieldKind.CHOICE:
        spec.choices = _choice_values(annotation)
    elif kind is FieldKind.MODEL:
        spec.model_type = annotation
    elif kind in (FieldKind.LIST, FieldKind.DICT):
        spec.inner_annotations = typing.get_args(annotation)
    elif kind is FieldKind.OPTIONAL:
        spec.optional = True
        spec.inner_annotations = _non_none_args(annotation)
    elif kind is FieldKind.UNION:
        spec.optional = len(_non_none_args(annotation)) != len(typing.get_args(annotation))
        spec.inner_annotations = _non_none_args(annotation)
    elif kind is FieldKind.TAGGED_UNION:
        tagged = _tagged_union_members(annotation)
        if tagged is not None:
            spec.discriminator, spec.union_members = tagged
            # 判别联合渲染为单卡(ComboBox 切 kind);字段无 icon 时回退到成员模型自带 icon。
            # 成员各自标 icon 时取第一个作代表(本项目规则模型共用同一 icon,无歧义)。
            if spec.icon is None:
                for _, member in spec.union_members:
                    member_icon = _model_icon_of(member)
                    if member_icon is not None:
                        spec.icon = member_icon
                        break

    return spec


def _choice_values(annotation: Any) -> list[Any]:
    if typing.get_origin(annotation) is Literal:
        return list(typing.get_args(annotation))
    if _is_enum(annotation):
        return [member.value for member in annotation]
    return []


def iter_field_specs(
    model_type: type[BaseModel],
    *,
    choices_providers: Mapping[str, ChoicesProvider] | None = None,
) -> list[FieldSpec]:
    """遍历模型字段,产出可见字段的 FieldSpec(隐藏字段跳过)。

    隐藏由模型字段的 exclude / json_schema_extra={"hidden": True} 决定(单一事实源)。
    choices_providers 按字段名注入候选(如 device_index → 设备列表)。
    """

    providers = choices_providers or {}
    specs: list[FieldSpec] = []
    for name, info in model_type.model_fields.items():
        if is_hidden(info):
            continue
        specs.append(build_field_spec(name, info, choices_provider=providers.get(name)))
    return specs

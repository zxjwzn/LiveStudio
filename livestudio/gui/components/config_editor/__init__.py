"""通用 Pydantic 配置编辑组件

基于模型字段元信息(model_fields/FieldInfo)自动生成可编辑表单,支持嵌套/列表/字典/
联合/Optional,exotic 子树只读兜底。保存经 model_validate 全量校验后回传新实例。
"""

from ._schema_types import ChoiceItem, ChoicesProvider, FieldKind, FieldSpec
from .editor import ConfigEditor, SaveHandler

__all__ = [
    "ChoiceItem",
    "ChoicesProvider",
    "ConfigEditor",
    "FieldKind",
    "FieldSpec",
    "SaveHandler",
]

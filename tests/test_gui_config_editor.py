"""测试通用配置编辑器链路（P5+）

覆盖：
- ChoicesRegistry：注册/解析/缺失返回空
- WidgetRegistry：auto 解析默认控件、自定义 renderer 覆盖、未知 widget 兜底
- schema_introspect：Pydantic 模型反射（类型/约束/默认/枚举/Optional 解包/嵌套 group/覆盖层）
- ConfigEditor：按字段渲染、group 递归、on_change 增量回调、动态下拉异步拉取
- AudioController：设备枚举为 ChoiceVM、配置反射与单字段写回

注：用假后端/假 page，不接真实麦克风。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import flet as ft
from pydantic import BaseModel, ConfigDict, Field

from livestudio.gui.bridge.schema_introspect import FieldOverride, introspect_model
from livestudio.gui.components.config_editor import (
    ConfigEditor,
    default_widget_registry,
)
from livestudio.gui.core.choices_registry import ChoicesRegistry
from livestudio.gui.core.view_models import ChoiceVM, ConfigFieldVM
from livestudio.gui.core.widget_registry import RenderContext, WidgetRegistry

# —— ChoicesRegistry ————————————————————————————————————————


async def test_choices_registry_register_resolve_and_missing() -> None:
    """注册后能解析；未注册返回空列表；has 反映存在性"""
    registry = ChoicesRegistry()

    async def provider() -> list[ChoiceVM]:
        return [ChoiceVM(value="a", label="A"), ChoiceVM(value="b", label="B")]

    registry.register("src", provider)
    assert registry.has("src") is True
    assert registry.has("missing") is False
    choices = await registry.resolve("src")
    assert [c.value for c in choices] == ["a", "b"]
    assert await registry.resolve("missing") == []


# —— WidgetRegistry ————————————————————————————————————————


def test_widget_registry_auto_resolves_default_widget() -> None:
    """widget=auto 时按 value_type 解析到默认控件 key"""
    registry = default_widget_registry()
    assert registry.resolve_widget_key(ConfigFieldVM(path="p", label="l", value_type="bool")) == "switch"
    assert registry.resolve_widget_key(ConfigFieldVM(path="p", label="l", value_type="int")) == "number"
    assert registry.resolve_widget_key(ConfigFieldVM(path="p", label="l", value_type="enum")) == "dropdown"


def test_widget_registry_explicit_widget_overrides_auto() -> None:
    """显式 widget 覆盖 auto 默认"""
    registry = default_widget_registry()
    # value_type=int 默认 number；显式 widget=text 应覆盖默认
    field = ConfigFieldVM(path="p", label="l", value_type="int", widget="text")
    assert registry.resolve_widget_key(field) == "text"


def test_widget_registry_custom_renderer_registers_and_renders() -> None:
    """注册自定义控件 renderer 后可被 render 解析"""
    registry = WidgetRegistry()
    marker = ft.Text("knob")
    registry.register("knob", lambda _ctx: marker)
    field = ConfigFieldVM(path="p", label="l", value_type="float", widget="knob")
    ctx = RenderContext(field=field, emit=lambda _v: None)
    assert registry.render(ctx) is marker


def test_widget_registry_unknown_widget_returns_none() -> None:
    """未注册的 widget 返回 None（编辑器据此兜底）"""
    registry = WidgetRegistry()
    field = ConfigFieldVM(path="p", label="l", value_type="float", widget="nope")
    ctx = RenderContext(field=field, emit=lambda _v: None)
    assert registry.render(ctx) is None


# —— schema_introspect ————————————————————————————————————————


class _Nested(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag: bool = Field(default=True, description="开关")


class _Sample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="名称")
    count: int = Field(default=3, ge=1, le=10, description="数量")
    ratio: float = Field(default=0.5, gt=0.0, lt=1.0, description="比例")
    mode: str = Field(default="x", description="模式")  # 覆盖成枚举
    nested: _Nested = Field(default_factory=_Nested, description="子组")


def test_introspect_infers_types_constraints_defaults() -> None:
    """类型/约束/默认/说明自动反射，Optional[int] 解包为 int"""
    section = introspect_model(_Sample(), section_id="s", title="样例")
    by_path = {f.path: f for f in section.fields}

    assert by_path["name"].value_type == "str"  # Optional[str] -> str
    assert by_path["name"].help == "名称"

    count = by_path["count"]
    assert count.value_type == "int"
    assert count.min == 1.0
    assert count.max == 10.0
    assert count.default == 3

    ratio = by_path["ratio"]
    assert ratio.value_type == "float"
    assert ratio.min == 0.0  # gt 也作为 min
    assert ratio.max == 1.0


def test_introspect_nested_model_becomes_group() -> None:
    """嵌套 BaseModel 递归成 group，子字段路径带前缀"""
    section = introspect_model(_Sample(), section_id="s", title="样例")
    nested = next(f for f in section.fields if f.path == "nested")
    assert nested.value_type == "group"
    assert len(nested.fields) == 1
    assert nested.fields[0].path == "nested.flag"
    assert nested.fields[0].value_type == "bool"


def test_introspect_overrides_label_widget_choices_hidden() -> None:
    """覆盖层：改标题/控件、绑动态源、隐藏字段"""
    section = introspect_model(
        _Sample(),
        section_id="s",
        title="样例",
        overrides={
            "name": FieldOverride(label="名字", widget="dropdown", choices_source="things"),
            "count": FieldOverride(label="数量", widget="number"),
            "ratio": FieldOverride(hidden=True),
        },
    )
    by_path = {f.path: f for f in section.fields}
    assert "ratio" not in by_path  # 已隐藏

    name = by_path["name"]
    assert name.label == "名字"
    assert name.value_type == "enum"  # 绑动态源强制 enum
    assert name.widget == "dropdown"
    assert name.choices_source == "things"

    assert by_path["count"].widget == "number"


def test_introspect_reads_gui_metadata_from_model() -> None:
    """模型 json_schema_extra 的 gui_* 元数据作为基线被反射读取"""

    class _Meta(BaseModel):
        model_config = ConfigDict(extra="forbid")
        dev: str | None = Field(
            default=None,
            description="设备",
            json_schema_extra={"gui_label": "输入设备", "gui_widget": "dropdown", "gui_choices_source": "devs"},
        )
        secret: int = Field(default=0, json_schema_extra={"gui_hidden": True})

    section = introspect_model(_Meta(), section_id="s", title="t")
    by_path = {f.path: f for f in section.fields}

    assert "secret" not in by_path  # gui_hidden 生效
    dev = by_path["dev"]
    assert dev.label == "输入设备"
    assert dev.widget == "dropdown"
    assert dev.value_type == "enum"  # 绑动态源强制 enum
    assert dev.choices_source == "devs"


def test_introspect_code_override_beats_model_metadata() -> None:
    """代码侧 FieldOverride 优先于模型 json_schema_extra"""

    class _Meta(BaseModel):
        model_config = ConfigDict(extra="forbid")
        x: int = Field(default=1, json_schema_extra={"gui_label": "模型标签"})

    section = introspect_model(
        _Meta(),
        section_id="s",
        title="t",
        overrides={"x": FieldOverride(label="代码标签")},
    )
    assert section.fields[0].label == "代码标签"


def test_introspect_literal_becomes_enum_choices() -> None:
    """Literal[...] 字段反射成 enum + 静态 choices"""

    class _WithLiteral(BaseModel):
        model_config = ConfigDict(extra="forbid")
        kind: str = Field(default="a", description="类型")

    # 用真实 Literal 注解的模型（音频 dtype 即此形态）
    from typing import Literal

    class _Lit(BaseModel):
        model_config = ConfigDict(extra="forbid")
        dtype: Literal["f32", "i16"] = Field(default="f32", description="格式")

    section = introspect_model(_Lit(), section_id="s", title="t")
    dtype = section.fields[0]
    assert dtype.value_type == "enum"
    assert {c.value for c in dtype.choices} == {"f32", "i16"}


# —— ConfigEditor ————————————————————————————————————————————


class _FakePage:
    def __init__(self) -> None:
        self.tasks: list = []

    def run_task(self, handler) -> None:
        assert asyncio.iscoroutinefunction(handler), "run_task 需要协程函数"
        self.tasks.append(handler)

    def update(self, *controls) -> None:  # noqa: ARG002
        pass


def _mount(editor: ConfigEditor) -> _FakePage:
    page = _FakePage()
    editor.page = cast(Any, page)
    return page


def test_config_editor_renders_one_control_per_field() -> None:
    """每个非 group 字段渲染一个顶层控件"""
    fields = [
        ConfigFieldVM(path="a", label="A", value_type="bool"),
        ConfigFieldVM(path="b", label="B", value_type="str", value="hi"),
        ConfigFieldVM(path="c", label="C", value_type="int", value=5),
    ]
    editor = ConfigEditor(fields, on_change=lambda _p, _v: None)
    assert len(editor.controls) == 3


def test_config_editor_group_renders_recursively() -> None:
    """group 字段递归渲染子字段"""
    group = ConfigFieldVM(
        path="g",
        label="组",
        value_type="group",
        fields=(
            ConfigFieldVM(path="g.x", label="X", value_type="bool"),
            ConfigFieldVM(path="g.y", label="Y", value_type="int", value=1),
        ),
    )
    editor = ConfigEditor([group], on_change=lambda _p, _v: None)
    assert len(editor.controls) == 1  # 一个 group 块


def test_config_editor_emits_path_and_value_on_change() -> None:
    """控件改动经 on_change 上报 (path, value)"""
    captured: list = []
    fields = [ConfigFieldVM(path="a.b", label="A", value_type="bool", value=False)]
    editor = ConfigEditor(fields, on_change=lambda p, v: captured.append((p, v)))
    switch = _find(editor, ft.Switch)
    switch.on_change(cast(Any, type("E", (), {"control": switch})()))
    switch.value = True
    switch.on_change(cast(Any, type("E", (), {"control": switch})()))
    assert captured[-1][0] == "a.b"


def test_config_editor_number_validates_type_and_bounds() -> None:
    """数值文本框：按 value_type 解析为 int、越界提示错误且不 emit、合法才提交"""
    captured: list = []
    fields = [
        ConfigFieldVM(
            path="mic.channels",
            label="声道数",
            value_type="int",
            value=1,
            min=1,
            max=8,
        )
    ]
    editor = ConfigEditor(fields, on_change=lambda p, v: captured.append((p, v)))
    text_field = _find(editor, ft.TextField)

    # 非数字：报错且不 emit
    text_field.value = "abc"
    text_field.on_blur(cast(Any, type("E", (), {"control": text_field})()))
    assert text_field.error_text is not None
    assert captured == []

    # 越界：报错且不 emit
    text_field.value = "99"
    text_field.on_blur(cast(Any, type("E", (), {"control": text_field})()))
    assert text_field.error_text is not None
    assert captured == []

    # 合法整数：清除错误并提交为 int
    text_field.value = "4"
    text_field.on_blur(cast(Any, type("E", (), {"control": text_field})()))
    assert not text_field.error_text  # Flet 把 None 归一为 ""，这里只校验“无错误”
    assert captured == [("mic.channels", 4)]
    assert isinstance(captured[0][1], int)


async def test_config_editor_dynamic_dropdown_loads_via_registry() -> None:
    """choices_source 字段挂载即经 registry 异步拉取选项"""
    registry = ChoicesRegistry()

    async def provider() -> list[ChoiceVM]:
        return [ChoiceVM(value="dev1", label="设备一")]

    registry.register("devs", provider)

    field = ConfigFieldVM(
        path="dev",
        label="设备",
        value_type="enum",
        widget="dropdown",
        choices_source="devs",
    )
    page = _FakePage()
    editor = ConfigEditor(
        [field],
        on_change=lambda _p, _v: None,
        choices_registry=registry,
        scheduler=lambda factory: page.tasks.append(factory),
    )
    editor.page = cast(Any, page)
    # 渲染时已调度异步拉取
    assert len(page.tasks) == 1
    await page.tasks[0]()
    dropdown = _find(editor, ft.Dropdown)
    assert [o.key for o in dropdown.options] == ["dev1"]


# —— AudioController 设备暂存 ——


def test_stage_device_name_clears_stale_index() -> None:
    """暂存新设备名时清空旧 device_index（否则后端按旧索引解析，换设备无效）"""
    from livestudio.gui.bridge.audio_controller import AudioController
    from livestudio.services.audio_stream.sources.microphone.config import (
        MicrophoneAudioStreamConfig,
    )

    mic = MicrophoneAudioStreamConfig(device_name="Mic A", device_index=5)
    router = type(
        "_Router",
        (),
        {"config": type("_Cfg", (), {"microphone": mic})()},
    )()
    controller = AudioController(cast(Any, type("_S", (), {})()), cast(Any, router))

    controller.stage_microphone_field("microphone.device_name", "Mic B")
    assert mic.device_name == "Mic B"
    assert mic.device_index is None  # 旧索引被清空，回退按名称匹配


def _find(control: ft.Control, kind: type) -> Any:
    """深度优先在控件树里找到第一个 kind 实例。"""
    stack = [control]
    while stack:
        node = stack.pop()
        if isinstance(node, kind):
            return node
        content = getattr(node, "content", None)
        if content is not None:
            stack.append(content)
        controls = getattr(node, "controls", None)
        if controls:
            stack.extend(controls)
    raise AssertionError(f"未找到 {kind.__name__}")

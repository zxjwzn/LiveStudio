"""MCP 平台工具集抽象

把「一个平台对 LLM 暴露的工具」收敛为一个 PlatformToolset 子类:子类只写带类型注解与
docstring 的 @tool 协程方法,方法体内调用 app 公开方法。基类通过内省把每个 @tool 方法
编译成 MCP Tool(name←方法名、description←docstring 主体、inputSchema←函数签名),并按名
分发调用、用自动生成的入参模型校验。子类不手写 Tool 对象、不手写 JSON Schema、不维护
工具清单,杜绝「方法与清单不同步」。

镜像 gui/bridge/platform_bridge.py 的角色:单平台对外抽象,基类给缺省,具体平台覆盖。
"""

from __future__ import annotations

import inspect
import typing
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import cached_property

import mcp.types as mcp_types
from pydantic import BaseModel, Field, create_model

from .constants import ARGS_HEADERS, TOOL_MARK


@dataclass(frozen=True, slots=True)
class _ToolMeta:
    """@tool 在方法上留下的标记:编译期据此生成 MCP Tool。"""

    name: str | None = None  # None → 用方法名


@dataclass(frozen=True, slots=True)
class _CompiledTool:
    """一个 @tool 方法的编译产物:发给 LLM 的 Tool + 入参模型 + 绑定方法。"""

    tool: mcp_types.Tool  # name / description / inputSchema
    input_model: type[BaseModel]  # 入参校验(由签名 + Args 说明构建)
    method: Callable[..., Awaitable[object]]  # 绑定到实例的协程方法


def tool(
    fn: Callable[..., Awaitable[object]] | None = None,
    *,
    name: str | None = None,
) -> Callable[..., Awaitable[object]] | Callable[[Callable[..., Awaitable[object]]], Callable[..., Awaitable[object]]]:
    """把一个带类型注解 + docstring 的协程方法标记为 MCP 工具。

    description 取自 docstring 主体,inputSchema 由函数签名 + docstring 的 Args 段自动生成
    (见 PlatformToolset 的编译逻辑)。支持 @tool 与 @tool(name="...") 两种写法。
    """

    def wrap(target: Callable[..., Awaitable[object]]) -> Callable[..., Awaitable[object]]:
        setattr(target, TOOL_MARK, _ToolMeta(name=name))
        return target

    return wrap if fn is None else wrap(fn)


def _split_doc(doc: str) -> tuple[str, dict[str, str]]:
    """把 docstring 切成 (工具描述主体, {参数名: 参数说明})。

    主体 = Args 小节之前的全部文字;Args 段按 "name: 说明" 逐行解析,续行(更深缩进且
    不含 "名: 值" 形态)并入上一参数说明。无 docstring 时返回 ("", {})。
    """

    body_lines: list[str] = []
    arg_docs: dict[str, str] = {}
    in_args = False
    last_arg: str | None = None
    for raw_line in doc.splitlines():
        stripped = raw_line.strip()
        if not in_args and stripped in ARGS_HEADERS:
            in_args = True
            continue
        if not in_args:
            body_lines.append(raw_line)
            continue
        if not stripped:
            continue
        arg_name, sep, desc = stripped.partition(":")
        if sep and " " not in arg_name.strip():
            last_arg = arg_name.strip()
            arg_docs[last_arg] = desc.strip()
        elif last_arg is not None:
            arg_docs[last_arg] = f"{arg_docs[last_arg]} {stripped}".strip()
    return "\n".join(body_lines).strip(), arg_docs


def _build_input_model(method: Callable[..., object], arg_docs: dict[str, str]) -> type[BaseModel]:
    """按方法签名 + Args 说明动态构建入参校验模型。

    遍历除 self 外的参数:类型注解作字段类型(缺注解即报错,构建期暴露),无默认值的
    参数为 required(...),Args 里的说明注入 Field(description=...)。
    """

    signature = inspect.signature(method)
    hints = typing.get_type_hints(method)
    fields: dict[str, object] = {}
    for param_name, param in signature.parameters.items():
        if param_name == "self":
            continue
        if param_name not in hints:
            raise TypeError(f"MCP 工具方法 {method.__name__} 的参数 {param_name} 缺少类型注解")
        annotation = hints[param_name]
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param_name] = (annotation, Field(default, description=arg_docs.get(param_name, "")))
    return create_model(f"{method.__name__}_Input", **fields)  # type: ignore[call-overload]


class PlatformToolset(ABC):
    """单平台对 LLM 暴露的工具集:子类写 @tool 方法,基类反射编译并分发。

    platform_name / description 抽象必填。子类把每个能力写成 @tool 协程方法,方法体内只调
    app 公开方法。tools() / call() 基于自动收集的注册表工作,子类不手维护工具清单。
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台唯一名称(switch_platform 的目标、工具路由键)"""

    @property
    @abstractmethod
    def description(self) -> str:
        """平台说明(list_platforms 展示给 LLM,帮助其判断该切到哪个平台)"""

    async def runtime_context(self) -> str:
        """可选:返回要随每次工具调用结果一起回给 LLM 的实时状态文本。

        由 server 在每次本平台工具调用成功后追加到 CallToolResult,使 LLM 每用一次工具就
        拿到一次最新状态(动态注入)。工具调用结果不经 client 缓存,故此通道永远实时,无需
        发 list_changed。默认空串(不注入);需要注入的平台覆盖此方法读 app 实时状态。
        """

        return ""

    @cached_property
    def _compiled(self) -> dict[str, _CompiledTool]:
        """反射收集本实例所有 @tool 方法,编译成 {工具名: 编译产物}。

        用 cached_property:绑定方法与 schema 在实例上算一次即固定(工具集随平台静态确定)。
        """

        compiled: dict[str, _CompiledTool] = {}
        # 扫描类 MRO 找带 @tool 标记的函数,再按名绑定到实例。不用 inspect.getmembers(self):
        # 它会遍历全部属性、触发本 cached_property 自身导致无限递归。
        seen: set[str] = set()
        for klass in type(self).__mro__:
            for attr_name, func in vars(klass).items():
                if attr_name in seen or not callable(func):
                    continue
                meta: _ToolMeta | None = getattr(func, TOOL_MARK, None)
                if meta is None:
                    continue
                seen.add(attr_name)
                method = getattr(self, attr_name)
                tool_name = meta.name or attr_name
                body, arg_docs = _split_doc(inspect.getdoc(method) or "")
                input_model = _build_input_model(func, arg_docs)
                schema = input_model.model_json_schema()
                schema.pop("title", None)  # pydantic 注入的模型名标题,对 LLM 无意义,去掉
                for prop in schema.get("properties", {}).values():
                    if isinstance(prop, dict):
                        prop.pop("title", None)  # 同理去掉每个参数的字段名标题
                if tool_name in compiled:
                    raise ValueError(f"平台 {self.platform_name} 存在重名 MCP 工具: {tool_name}")
                compiled[tool_name] = _CompiledTool(
                    tool=mcp_types.Tool(name=tool_name, description=body, inputSchema=schema),
                    input_model=input_model,
                    method=method,
                )
        return compiled

    def tools(self) -> list[mcp_types.Tool]:
        """该平台暴露给 LLM 的全部工具定义(供 server.list_tools 拼接到固有工具之后)。"""

        return [compiled.tool for compiled in self._compiled.values()]

    async def call(self, name: str, arguments: dict[str, object]) -> object:
        """按名分发工具调用:校验入参 → 调对应方法 → 返回其结果。

        工具名不属于本平台时抛 KeyError(由 server 收敛为对 LLM 的错误)。入参经自动生成
        的 pydantic 模型校验后以关键字参数传入方法。
        """

        compiled = self._compiled.get(name)
        if compiled is None:
            raise KeyError(f"平台 {self.platform_name} 无 MCP 工具: {name}")
        validated = compiled.input_model.model_validate(arguments)
        return await compiled.method(**validated.model_dump())

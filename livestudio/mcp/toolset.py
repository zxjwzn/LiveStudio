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
from typing import TYPE_CHECKING, Generic, TypeVar

import mcp.types as mcp_types
from pydantic import BaseModel, Field, create_model

from .constants import ARGS_HEADERS, TOOL_MARK

if TYPE_CHECKING:
    # 仅类型注解用:基类通用动词调 BasePlatformApp 的平台无关公开方法,运行时不引入 app 导入链。
    from livestudio.app.base import BasePlatformApp


@dataclass(frozen=True, slots=True)
class _ToolMeta:
    """@tool 在方法上留下的标记:编译期据此生成 MCP Tool。"""

    name: str | None = None  # None → 用方法名
    builtin: bool = False  # True → 固有通用动词(恒定可见,路由 active 平台)


@dataclass(frozen=True, slots=True)
class _CompiledTool:
    """一个 @tool 方法的编译产物:发给 LLM 的 Tool + 入参模型 + 绑定方法。"""

    tool: mcp_types.Tool  # name / description / inputSchema
    input_model: type[BaseModel]  # 入参校验(由签名 + Args 说明构建)
    method: Callable[..., Awaitable[object]]  # 绑定到实例的协程方法
    builtin: bool  # 固有通用动词(恒定可见);False 即平台特有(切到该平台才见)


def tool(
    fn: Callable[..., Awaitable[object]] | None = None,
    *,
    name: str | None = None,
    builtin: bool = False,
) -> Callable[..., Awaitable[object]] | Callable[[Callable[..., Awaitable[object]]], Callable[..., Awaitable[object]]]:
    """把一个带类型注解 + docstring 的协程方法标记为 MCP 工具。

    description 取自 docstring 主体,inputSchema 由函数签名 + docstring 的 Args 段自动生成
    (见 PlatformToolset 的编译逻辑)。支持 @tool 与 @tool(name="...") 两种写法。
    """

    def wrap(target: Callable[..., Awaitable[object]]) -> Callable[..., Awaitable[object]]:
        setattr(target, TOOL_MARK, _ToolMeta(name=name, builtin=builtin))
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


TApp = TypeVar("TApp", bound="BasePlatformApp")


class PlatformToolset(ABC, Generic[TApp]):
    """单平台对 LLM 暴露的工具集:子类写 @tool 方法,基类反射编译并分发。

    platform_name / description 抽象必填。子类把每个能力写成 @tool 协程方法,方法体内只调
    app 公开方法。tools() / call() 基于自动收集的注册表工作,子类不手维护工具清单。

    通用动词(connect / 情绪 / 控制器等,调 BasePlatformApp 上的平台无关方法)在基类以
    @tool(builtin=True) 声明,恒定为「固有」工具、路由到 active 平台;平台特有工具留在子类。
    泛型 TApp 收敛子类对具体 app 类型的访问,基类只依赖 BasePlatformApp 接口。
    """

    def __init__(self, app: TApp) -> None:
        self._app = app

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
        发 list_changed。默认注入表演时间线摘要;需要更多状态的平台覆盖此方法。
        """

        return f"timeline: {self._app.performance_summary()}"

    # --- 通用动词(平台无关,恒定为固有工具;调 BasePlatformApp 的平台无关方法) ---

    @tool(builtin=True)
    async def connect(self) -> str:
        """连接当前平台并加载模型。

        其它工具(动画、表情)都需先连接。重复连接是安全的(幂等)。连接后可用
        get_current_model 确认已加载的模型。
        """

        await self._app.connect()
        model = self._app.current_model
        if model is None:
            return "已连接平台，但当前未加载任何模型。"
        return f"已连接平台，当前模型：{model[1]}。"

    @tool(builtin=True)
    async def disconnect(self) -> str:
        """断开与当前平台的连接,并停止所有动画控制器。"""

        await self._app.disconnect()
        return "已断开平台连接。"

    @tool(builtin=True)
    async def get_current_model(self) -> dict[str, str | None]:
        """查询当前已加载的模型身份。

        返回 {model_id, model_name};未连接或未加载模型时两者为 null。
        """

        model = self._app.current_model
        if model is None:
            return {"model_id": None, "model_name": None}
        return {"model_id": model[0], "model_name": model[1]}

    # --- 待机动画控制器 ---

    @tool(builtin=True)
    async def start_idle_animations(self) -> str:
        """启动全部已启用的待机动画(眨眼、呼吸、注视等)。需已连接并加载模型。"""

        await self._app.start_controllers()
        return "已启动待机动画。"

    @tool(builtin=True)
    async def stop_idle_animations(self) -> str:
        """停止全部待机动画。"""

        await self._app.stop_controllers()
        return "已停止待机动画。"

    @tool(builtin=True)
    async def list_controllers(self) -> list[dict[str, object]]:
        """列出可独立启停的待机动画控制器及其当前状态。

        返回每项含 {name, running, enabled}:name 为控制器标识(供 set_controller 使用),
        running 是否运行中,enabled 是否在模型配置中启用(禁用的无法启动)。未连接/未加载
        模型时返回空列表。
        """

        return [
            {"name": status.name, "running": status.running, "enabled": status.enabled}
            for status in self._app.list_controllers()
        ]

    @tool(builtin=True)
    async def set_controller(self, name: str, running: bool) -> str:
        """启动或停止单个待机动画控制器(仅运行态,不改模型配置)。

        Args:
            name: 控制器标识,取自 list_controllers 返回的 name(如 "blink"/"breathing")。
            running: True 启动,False 停止。被模型配置禁用的控制器无法启动。
        """

        try:
            actual = await self._app.set_controller(name, running)
        except KeyError as exc:
            return f"控制器不存在：{name}（{exc}）"
        if running and not actual:
            return f"控制器「{name}」在模型配置中已禁用，无法启动。"
        return f"控制器「{name}」当前{'运行中' if actual else '已停止'}。"

    # --- 情绪表情解算(一次性) ---

    @tool(builtin=True)
    async def list_emotions(self) -> list[str]:
        """列出可触发的情绪标识(如 "joy"/"anger"/"sadness"/"neutral" 等)。"""

        return self._app.available_emotions()

    # --- 表演时间线(唯一表演入口:草稿事件组 + FIFO 队列 + 锚点调度) ---
    #
    # 没有即时 speak/play_emotion 工具。全部表演经:
    #   add_event* → enqueue_draft → (可选 get_job/list_jobs) → 需要打断时 remove_job
    # 两级 delay: add_event.delay 相对锚点; enqueue_draft.delay 相对 Job 进入 running。
    # speak.end = 音频呈现结束(不是 HTTP 断开)。未知时长靠 start/end 锚点编排,不估秒数。

    @tool(builtin=True)
    async def add_event(
        self,
        type: str,
        params: dict[str, object] | None = None,
        id: str | None = None,
        start_anchor: str = "group",
        start_phase: str = "start",
        delay: float = 0.0,
        end_anchor: str | None = None,
        end_phase: str = "end",
        end_delay: float = 0.0,
    ) -> dict[str, object]:
        """向「当前事件组(草稿)」添加一条表演事件——**唯一**的表演添加接口。

        没有独立的 speak/play_emotion 工具;说话、表情、原生表情、等待全部用本工具,
        用 type + params 区分。添加只改草稿,不会立刻演出;须再调 enqueue_draft 才入队执行。

        ## 事件类型 type 与 params

        - speak: 合成并播放文本。params 必填 text(非空字符串)。
          锚点: start=音频呈现首帧上总线; end=呈现播完(不是 TTS 网络断开)。
        - play_emotion: 情绪表情 oneshot。params 必填 emotion(取自 list_emotions);
          可选 intensity[0,1]、transition_duration、hold_duration(秒,>=0)。
          锚点: start=目标表情开始过渡时; end=开始回中性时(脸上可能仍在回落)。
        - set_native_expression: 瞬时开关原生表情。params 必填 name、active(bool)。
          start 与 end 同一时刻。
        - clear_native_expressions: 取消全部原生表情。params 用 {}。
        - wait: 纯延时。params 必填 seconds(>=0)。用于组内占位等待。

        ## 启动约束(何时真正执行)

        事件在「start_anchor 的 start_phase 发生」之后再等 delay 秒才调用底层能力:
        - start_anchor="group"(默认): 本 Job 开演时刻(已含 enqueue_draft 的 delay)。
        - start_anchor="<事件id>": 同组内另一事件的 id(必须先 add 再引用)。
        - start_phase="start"(默认) 或 "end"。
        - delay: 相对该锚点后再推迟的秒数(>=0,默认 0)。

        多个事件都默认 group.start+0 时会**并行**启动(例如同时说话+表情)。

        ## 结束约束 end_*（通用,与 type 无关）

        可选 end_anchor / end_phase / end_delay:到点后调度器**强制释放**该事件
        (speak→停播, play_emotion→取消保持并回中性, 其它 type 按能力释放)。
        未设 end 时按该动作自然结束。这是通用生命周期,不是 play_emotion 专用参数。

        表情撑到语音播完:
          add_event(type="speak", params={"text":"……"}, id="s")
          add_event(type="play_emotion", params={"emotion":"joy"},
                    start_anchor="s", start_phase="start", delay=0,
                    end_anchor="s", end_phase="end", end_delay=0)
          enqueue_draft()

        同组内多个 speak 不得可能重叠:后一句须绑前一句 end,否则 enqueue 会拒绝。

        ## 推荐编排示例

        开口后 2 秒笑:
          add_event(type="speak", params={"text":"你好"}, id="s")
          add_event(type="play_emotion", params={"emotion":"joy"},
                    start_anchor="s", start_phase="start", delay=2)
          enqueue_draft()

        说完再表情:
          add_event(type="speak", params={"text":"……"}, id="s")
          add_event(type="play_emotion", params={"emotion":"sadness"},
                    start_anchor="s", start_phase="end", delay=0)
          enqueue_draft()

        整段计划轮到执行后再晚 5 秒开演:
          add_event(...)
          enqueue_draft(delay=5)

        ## 返回

        整个草稿快照 {events, valid, errors}。valid=false 时 errors 说明原因
        (未知 type、缺参数、锚点不存在、依赖成环、id 重复等),该条未写入。
        成功时可用返回的 id 给后续 add_event 做 start_anchor。

        Args:
            type: 事件类型:speak / play_emotion / set_native_expression /
                clear_native_expressions / wait。
            params: 与 type 匹配的参数对象。speak 需 {"text":"..."};
                play_emotion 需 {"emotion":"joy"} 等;wait 需 {"seconds":1.0}。
                可传 null 等价 {}。
            id: 可选事件 id,组内唯一;不传则自动生成 e1,e2…。需要被其它事件
                引用时建议显式指定简短 id。
            start_anchor: 启动锚点。"group" 表示本计划开演,或同组事件 id。默认 group。
            start_phase: 相对锚点的相位:"start" 或 "end"。默认 start。
            delay: 相对 start 锚点后再等待的秒数(>=0)。默认 0。
            end_anchor: 可选结束锚点。"group" 或事件 id;不传表示自然结束。
            end_phase: 结束锚点相位 "start"|"end";默认 end。
            end_delay: 相对 end 锚点后再等的秒数(>=0)。默认 0。
        """

        return self._app.performance_add_event(
            type,
            params,
            id=id,
            start_anchor=start_anchor,
            start_phase=start_phase,
            delay=delay,
            end_anchor=end_anchor,
            end_phase=end_phase,
            end_delay=end_delay,
        )

    @tool(builtin=True)
    async def remove_event(self, event_id: str) -> dict[str, object]:
        """从当前事件组(草稿)删除一条事件。

        仅作用于尚未 enqueue 的草稿;已入队 Job 不可改事件,只能 remove_job 整单删除/取消。
        若仍有其它草稿事件的 start_anchor 指向本 id,删除会被拒绝(errors 提示先删依赖方)。

        返回更新后的草稿快照 {events, valid, errors}。

        Args:
            event_id: 草稿中的事件 id(add_event 返回或自指定的 id)。
        """

        return self._app.performance_remove_event(event_id)

    @tool(builtin=True)
    async def get_draft(self) -> dict[str, object]:
        """查看当前事件组(草稿):尚未入队的事件列表与校验结果。

        返回 {events:[{id,type,params,start}], valid, errors}。
        enqueue 前可用本工具自检;valid=false 时不要 enqueue,先按 errors 修正。
        入队成功后草稿会被清空,此时 events 为空。
        """

        return self._app.performance_get_draft()

    @tool(builtin=True)
    async def clear_draft(self) -> dict[str, object]:
        """清空当前事件组草稿(丢弃所有未入队事件)。

        不影响已在队列中 running/pending 的 Job。返回空草稿快照。
        """

        return self._app.performance_clear_draft()

    @tool(builtin=True)
    async def enqueue_draft(self, delay: float = 0.0) -> dict[str, object]:
        """把当前事件组**快照入队**并清空草稿,开始(或排队等待)执行。

        ## 队列语义(重要)

        - 全局 FIFO:**同时最多一个 running Job**。
        - 队列空闲:本 Job 立即变为 running 并开始调度。
        - 已有 running:本 Job 进入 pending 队尾,**不会打断**当前演出。
        - 想插播/覆盖:先 remove_job 取消 running(或 all=true),再 enqueue。
        - 空草稿、校验失败、多个 speak 可能重叠 → ok=false,草稿保留不动。

        ## delay(计划级推迟)

        delay 是「本 Job **变成 running 之后**再等多少秒才 group.start」,
        **不是**「从现在起多少秒」。前面 Job 拖得久,本单仍在 pending 排着,
        轮到自己后才开始数 delay。

        与 add_event.delay 叠加:先 enqueue_delay,再事件相对锚点的 delay。

        ## 返回

        {ok, job_id, state(running|pending), position, queue_size, start_delay,
         draft, queue, error?, message?}。失败时看 error/message 与 draft.errors。

        Args:
            delay: 轮到执行后再推迟开演的秒数(>=0)。默认 0 表示一 running 立即开演。
        """

        return await self._app.performance_enqueue_draft(delay=delay)

    @tool(builtin=True)
    async def list_jobs(self, include_finished: bool = False, limit: int = 20) -> dict[str, object]:
        """列出表演队列状态:当前 running、等待中的 pending、可选近期 finished。

        用来确认「还在播吗 / 后面排了几单 / 上单是否成功」。
        每次其它工具结果的 runtime_context 也会带 timeline 一行摘要,本工具给完整结构。

        返回 {running: JobSnapshot|null, pending:[...], finished:[...]}。
        JobSnapshot 含 job_id、state、enqueue_delay、phase、events 状态列表等。

        Args:
            include_finished: 是否附带已结束 Job(completed/cancelled/failed);默认 false。
            limit: finished 最多返回条数;默认 20。
        """

        return self._app.performance_list_jobs(include_finished=include_finished, limit=limit)

    @tool(builtin=True)
    async def get_job(self, job_id: str) -> dict[str, object]:
        """查看指定 Job 的详情:各事件 status、是否已 start/end、错误信息。

        用于判断说话是否真正播完(事件 status=completed 且曾 running),
        不要靠猜测时长。job 不存在时返回 ok=false。

        事件 status: pending → armed → running → completed|cancelled|failed。
        Job state: pending|running|completed|cancelled|failed。
        running 时 phase 可能为 starting_delay(仍在 enqueue_delay 等待)或 playing。

        Args:
            job_id: enqueue_draft 成功时返回的 job_id。
        """

        snap = self._app.performance_get_job(job_id)
        if snap is None:
            return {"ok": False, "error": "not_found", "message": f"未找到 job: {job_id}"}
        return {"ok": True, "job": snap}

    @tool(builtin=True)
    async def remove_job(self, job_id: str | None = None, all: bool = False) -> dict[str, object]:
        """删除 pending Job,或**取消**正在执行的 Job(唯一打断入口)。

        - pending: 直接移出队列,不启动。
        - running: 停止 TTS、取消表情收尾、取消未触发定时器;cancelled 后自动启动下一个 pending。
        - all=true: 取消 running(若有)并清空全部 pending;job_id 可省略。

        新 add_event/enqueue **不能**覆盖正在跑的计划;必须先本工具取消再提交新编排。

        返回 {ok, removed:[job_id...], cancelled_running, message?, queue?}。

        Args:
            job_id: 要删除或取消的 job_id。all=true 时可省略;否则必填。
            all: true 时清空整个队列(取消 running + 丢弃 pending)。默认 false。
        """

        return await self._app.performance_remove_job(job_id, all=all)

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
                    builtin=meta.builtin,
                )
        return compiled

    def tools(self) -> list[mcp_types.Tool]:
        """该平台的特有工具定义(非固有);固有通用动词见 universal_tools()。"""

        return [compiled.tool for compiled in self._compiled.values() if not compiled.builtin]

    def universal_tools(self) -> list[mcp_types.Tool]:
        """固有通用动词定义(平台无关,恒定可见,路由到 active 平台)。"""

        return [compiled.tool for compiled in self._compiled.values() if compiled.builtin]

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

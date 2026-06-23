"""日志页（P5 完善）。

订阅 ``state.logs``，提供:
- 级别下拉过滤（ALL / TRACE / DEBUG / INFO / SUCCESS / WARNING / ERROR / CRITICAL）
- 关键字过滤（仅匹配 message，本地筛选不回写状态）
- 暂停（仅停止 UI 追加，缓冲继续）
- 清空（仅清当前视图列表，不动 state.logs）
- 自动滚动开关
"""

from __future__ import annotations

import asyncio

import flet as ft

from ..core.base_view import BaseView
from ..core.observable import items_after_anchor
from ..core.theme import PALETTE, TYPE, level_color
from ..core.view_models import LogEntryVM

_LEVELS: tuple[str, ...] = ("ALL", "TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL")
_LEVEL_PRIORITY: dict[str, int] = {name: i for i, name in enumerate(_LEVELS)}

# 视图显示行数硬上限：state.logs 缓冲可达 2000 条，但一次性渲染上千个 flet
# 控件会在事件循环线程内同步序列化推送，阻塞 drain/平台/音频等所有 async 任务。
# 故视图只渲染最近 _VIEW_CAP 条，超出的旧行从 ListView 头部裁掉。
_VIEW_CAP = 500
# 过滤输入防抖：关键字逐字符触发全量重渲染开销大，合并到一次。
_FILTER_DEBOUNCE_SECONDS = 0.25


class LogsView(BaseView):
    """日志视图：订阅 AppState.logs 实时渲染 + 本地过滤/暂停/清空。"""

    def build_content(self) -> ft.Control:
        # —— 视图本地状态（不回写 AppState）——
        self._level_filter: str = "ALL"
        self._keyword: str = ""
        self._paused: bool = False
        self._auto_scroll: bool = True
        # 清空锚点：清空时记录最后一条日志对象；渲染只取锚点之后的日志，
        # 避免新日志触发重渲染时把已清空的旧日志重新铺出来。锚点被环形缓冲
        # 丢弃时，当前缓冲里的都是更新的日志，自然全部展示。
        self._clear_anchor: LogEntryVM | None = None
        # 增量渲染锚点：记录已渲染进列表的最后一条日志对象。日志推送时只追加其
        # 之后的新行，避免每次 flush 全量重建整个 ListView；锚点被环形缓冲丢弃
        # 时回退到全量重建。过滤条件变化/清空/暂停恢复仍走全量 _render。
        self._rendered_anchor: LogEntryVM | None = None
        # 过滤防抖：关键字逐字符输入会触发全量重渲染，用 epoch 计数器合并。每次
        # 输入递增 epoch 并延迟调度，回调执行时若 epoch 已过期（有更新的输入）则跳过。
        self._filter_epoch: int = 0

        # —— 工具栏控件 ——
        self._level_dropdown = ft.Dropdown(
            label="级别",
            value="ALL",
            width=140,
            on_change=self._on_level_change,
            options=[ft.dropdown.Option(level) for level in _LEVELS],
        )
        self._keyword_field = ft.TextField(
            label="过滤关键字",
            hint_text="按消息内容过滤",
            prefix_icon=ft.Icons.SEARCH,
            on_change=self._on_keyword_change,
            expand=True,
            dense=True,
        )
        self._pause_button = ft.IconButton(
            icon=ft.Icons.PAUSE,
            icon_color=PALETTE.primary_hover,
            tooltip="暂停",
            on_click=self._on_pause_click,
        )
        self._clear_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            icon_color=PALETTE.text_muted,
            tooltip="清空当前视图（不动状态缓冲）",
            on_click=self._on_clear_click,
        )
        self._auto_scroll_switch = ft.Switch(
            label="自动滚动",
            value=True,
            on_change=self._on_auto_scroll_change,
            active_color=PALETTE.primary,
        )

        toolbar = ft.Row(
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                self._level_dropdown,
                self._keyword_field,
                self._pause_button,
                self._clear_button,
                self._auto_scroll_switch,
            ],
        )

        # —— 日志列表 ——
        self._list = ft.ListView(expand=True, spacing=2, auto_scroll=True, padding=12)
        self._empty = ft.Container(
            content=ft.Text("暂无日志", color=PALETTE.text_muted, size=TYPE.body),
            alignment=ft.alignment.center,
            expand=True,
        )
        self._body = ft.Container(
            content=self._empty,
            expand=True,
            bgcolor=PALETTE.surface,
            border=ft.border.all(1, PALETTE.border),
            border_radius=ft.border_radius.all(12),
        )

        return ft.Column(
            expand=True,
            spacing=14,
            controls=[
                ft.Text("日志", size=TYPE.title, weight=ft.FontWeight.W_600, color=PALETTE.text),
                toolbar,
                self._body,
            ],
        )

    # —— 订阅 ——
    def bind(self) -> None:
        self.watch(self.state.logs, self._on_logs)

    def _on_logs(self, entries: list[LogEntryVM]) -> None:
        if self._paused:
            return
        self._append_new(entries)

    def _append_new(self, entries: list[LogEntryVM]) -> None:
        """增量追加：只渲染上次渲染锚点之后的新日志，避免每次 flush 全量重建。

        锚点（上次已渲染的最后一条）仍在缓冲里 → 仅对其后的新条目过滤后 append；
        锚点为 None（首次）或已被环形缓冲丢弃 → 回退到全量 _render。
        """

        anchor = self._rendered_anchor
        if anchor is None:
            self._render(entries)
            return
        new_entries = items_after_anchor(entries, anchor)
        # 锚点已被丢弃时 items_after_anchor 返回全部，与「仅新增」语义不符，回退全量
        if len(new_entries) == len(entries):
            self._render(entries)
            return
        if not new_entries:
            return
        new_rows = [self._row(entry) for entry in new_entries if self._matches(entry)]
        self._rendered_anchor = entries[-1]
        if not new_rows:
            return
        self._list.controls.extend(new_rows)
        self._trim_controls()
        self._list.auto_scroll = self._auto_scroll
        self._body.content = self._list
        self.safe_update()

    def _render(self, entries: list[LogEntryVM]) -> None:
        visible = items_after_anchor(entries, self._clear_anchor)
        filtered = [entry for entry in visible if self._matches(entry)]
        # 只渲染最近 _VIEW_CAP 条：上千行一次性建控件会阻塞事件循环。超出部分丢弃，
        # 旧日志仍可在 state.logs 缓冲里（此处仅限制 UI 同时展示的行数）。
        if len(filtered) > _VIEW_CAP:
            filtered = filtered[-_VIEW_CAP:]
        # 始终重建列表内容：筛选后为空也要清掉旧行，否则切回列表时残留上次的行
        self._list.controls = [self._row(entry) for entry in filtered]
        self._list.auto_scroll = self._auto_scroll
        self._body.content = self._empty if not filtered else self._list
        # 记录已渲染锚点，供后续增量追加判断起点
        self._rendered_anchor = entries[-1] if entries else None
        self.safe_update()

    def _trim_controls(self) -> None:
        """增量追加后裁剪列表头部，保持显示行数不超过 _VIEW_CAP。"""

        overflow = len(self._list.controls) - _VIEW_CAP
        if overflow > 0:
            del self._list.controls[:overflow]

    # —— 过滤逻辑 ——
    def _matches(self, entry: LogEntryVM) -> bool:
        if self._level_filter != "ALL":
            min_prio = _LEVEL_PRIORITY.get(self._level_filter, 0)
            entry_prio = _LEVEL_PRIORITY.get(entry.level.upper(), 0)
            if entry_prio < min_prio:
                return False
        if not self._keyword:
            return True
        return self._keyword.lower() in entry.message.lower()

    # —— 工具栏回调 ——
    def _on_level_change(self, e: ft.ControlEvent) -> None:
        self._level_filter = e.control.value or "ALL"
        self._render(self.state.logs.value)

    def _on_keyword_change(self, e: ft.ControlEvent) -> None:
        self._keyword = (e.control.value or "").strip()
        self._schedule_filter_render()

    def _schedule_filter_render(self) -> None:
        """防抖：逐字符输入合并为一次重渲染。

        有运行中事件循环时递增 epoch 并延迟调度，回调执行时若 epoch 已过期
        （期间又有新输入）则跳过；无事件循环（如单元测试同步驱动）时直接同步渲染，
        保证调用后立即可断言。
        """

        self._filter_epoch += 1
        epoch = self._filter_epoch
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._render(self.state.logs.value)
            return

        async def _debounced() -> None:
            await asyncio.sleep(_FILTER_DEBOUNCE_SECONDS)
            if epoch == self._filter_epoch:
                self._render(self.state.logs.value)

        loop.create_task(_debounced())

    def _on_pause_click(self, _e: ft.ControlEvent) -> None:
        self._paused = not self._paused
        if self._paused:
            self._pause_button.icon = ft.Icons.PLAY_ARROW
            self._pause_button.tooltip = "继续"
        else:
            self._pause_button.icon = ft.Icons.PAUSE
            self._pause_button.tooltip = "暂停"
            # 继续时立即拉一次最新
            self._render(self.state.logs.value)
        self.safe_update()

    def _on_clear_click(self, _e: ft.ControlEvent) -> None:
        # 仅清空当前视图：把锚点设为当前最后一条日志，此后只渲染其之后的新日志。
        # state.logs 缓冲不动；新日志触发重渲染时不会再把已清空的旧日志带回来。
        entries = self.state.logs.value
        self._clear_anchor = entries[-1] if entries else None
        # 增量锚点同步到清空点，否则下次 flush 会从旧锚点把已清空的行重新铺出来
        self._rendered_anchor = self._clear_anchor
        self._list.controls = []
        self._body.content = self._empty
        self.safe_update()

    def _on_auto_scroll_change(self, e: ft.ControlEvent) -> None:
        self._auto_scroll = bool(e.control.value)
        self._list.auto_scroll = self._auto_scroll
        self.safe_update()

    # —— 行渲染 ——
    def _row(self, entry: LogEntryVM) -> ft.Control:
        # 单个 Text + TextSpan：span 是数据而非控件，每行只占 1 个 flet 控件
        # （旧实现为 1 Row + 3 Text = 4 控件，且 selectable=True 在 Flutter 侧
        # 开销大）。500 行即 500 控件，大幅降低 update 的序列化/diff 成本。
        return ft.Text(
            size=TYPE.caption,
            selectable=True,
            spans=[
                ft.TextSpan(
                    f"{entry.ts}  ",
                    ft.TextStyle(color=PALETTE.text_muted, font_family="monospace"),
                ),
                ft.TextSpan(
                    f"{entry.level:<8} ",
                    ft.TextStyle(color=level_color(entry.level), weight=ft.FontWeight.W_600),
                ),
                ft.TextSpan(entry.message, ft.TextStyle(color=PALETTE.text)),
            ],
        )

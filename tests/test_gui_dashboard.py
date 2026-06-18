"""测试 P3 仪表盘视图与组件

覆盖：
- AudioMeter：电平刷新与未激活态文案
- ControllerCard：idle/oneshot 按钮形态
- ExpressionButton：标签拼装
- DashboardView：连接/电平/控制器/表情四区随状态刷新
- DashboardView：启停/触发意图转发到 bridge 适配器（用假 page.run_task 捕获）

注：不渲染真实 Flet 窗口；用假 page 捕获 run_task 调度的协程并手动 await。
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import flet as ft

from livestudio.gui.components.audio_meter import AudioMeter
from livestudio.gui.components.controller_card import ControllerCard
from livestudio.gui.components.expression_button import ExpressionButton
from livestudio.gui.core.app_state import AppState
from livestudio.gui.core.view_context import ViewContext
from livestudio.gui.core.view_models import (
    AudioLevelVM,
    AudioSourceKind,
    ConnectionState,
    ControllerState,
    ControllerVM,
    ExpressionVM,
    PlatformStatusVM,
)
from livestudio.gui.views.dashboard import DashboardView


def _click(control: ft.Control) -> None:
    target = cast(Any, control)
    on_click = cast(ft.OptionalEventCallable[ft.ControlEvent], target.on_click)
    assert on_click is not None
    on_click(cast(ft.ControlEvent, None))


def _text(value: str | None) -> str:
    assert value is not None
    return value


class _FakePage:
    """假 page：捕获 run_task 调度的协程工厂，便于断言意图。"""

    def __init__(self) -> None:
        self.tasks: list = []

    def run_task(self, handler) -> None:
        # 复刻真实 page.run_task 的断言：必须是协程函数（而非返回协程的普通 lambda）
        assert asyncio.iscoroutinefunction(handler), "run_task 需要协程函数"
        self.tasks.append(handler)

    def update(self, *controls) -> None:  # noqa: ARG002
        pass


class _FakeAdapter:
    """假平台适配器：记录被调用的意图。"""

    def __init__(self) -> None:
        self.toggled: list = []
        self.triggered: list = []

    async def set_controller_enabled(self, key: str, enabled: bool) -> None:
        self.toggled.append((key, enabled))

    async def trigger_expression(self, key: str) -> None:
        self.triggered.append(key)


class _FakeBridge:
    def __init__(self, adapter: _FakeAdapter) -> None:
        self._adapter = adapter

    def active_adapter(self) -> _FakeAdapter:
        return self._adapter


# —— 组件 ——————————————————————————————————————————————————


def test_audio_meter_updates_level_and_source() -> None:
    """AudioMeter 刷新 rms/peak 与音源文案，未激活时回退提示"""
    meter = AudioMeter()
    meter.update_level(
        AudioLevelVM(rms=0.4, peak=0.9, source=AudioSourceKind.MICROPHONE, active=True)
    )
    assert meter._rms_bar.value == 0.4
    assert meter._peak_bar.value == 0.9
    assert meter._source_text.value == "源: 麦克风"

    meter.update_level(AudioLevelVM(active=False))
    assert meter._source_text.value == "音频未启动"


def test_audio_meter_clamps_out_of_range() -> None:
    """电平超出 0..1 时被夹紧，避免 ProgressBar 报错"""
    meter = AudioMeter()
    meter.update_level(AudioLevelVM(rms=1.5, peak=-0.2, active=True))
    assert meter._rms_bar.value == 1.0
    assert meter._peak_bar.value == 0.0


def test_controller_card_idle_running_shows_pause() -> None:
    """idle 运行态控制器显示停止（pause）按钮，点击请求停止"""
    captured: list = []
    vm = ControllerVM(
        key="blink", display_name="眨眼", type="idle", state=ControllerState.RUNNING
    )
    card = ControllerCard(
        vm,
        on_toggle=lambda v, enabled: captured.append((v.key, enabled)),
        on_trigger=lambda v: captured.append(("trigger", v.key)),
    )
    button = _find_icon_button(card)
    assert button.icon == ft.Icons.PAUSE
    _click(button)
    assert captured == [("blink", False)]  # 运行中点击 -> 请求停止


def test_controller_card_idle_stopped_shows_play() -> None:
    """idle 停止态控制器显示启动（play）按钮，点击请求启动"""
    captured: list = []
    vm = ControllerVM(
        key="breathing", display_name="呼吸", type="idle", state=ControllerState.STOPPED
    )
    card = ControllerCard(
        vm,
        on_toggle=lambda v, enabled: captured.append((v.key, enabled)),
        on_trigger=lambda v: None,
    )
    button = _find_icon_button(card)
    assert button.icon == ft.Icons.PLAY_ARROW
    _click(button)
    assert captured == [("breathing", True)]


def test_controller_card_oneshot_triggers() -> None:
    """oneshot 控制器显示触发按钮，点击调用 on_trigger"""
    captured: list = []
    vm = ControllerVM(
        key="expression",
        display_name="表情解算",
        type="oneshot",
        state=ControllerState.STOPPED,
    )
    card = ControllerCard(
        vm,
        on_toggle=lambda v, enabled: None,
        on_trigger=lambda v: captured.append(v.key),
    )
    button = _find_icon_button(card)
    _click(button)
    assert captured == ["expression"]


def test_expression_button_label_and_click() -> None:
    """表情按钮拼装 emoji + 名称，点击回调带 vm"""
    captured: list = []
    vm = ExpressionVM(key="joy", display_name="喜悦", emoji="😊")
    button = ExpressionButton(vm, on_trigger=lambda v: captured.append(v.key))
    assert "喜悦" in _text(button.text)
    assert "😊" in _text(button.text)
    _click(button)
    assert captured == ["joy"]


def _find_icon_button(control: ft.Control) -> ft.IconButton:
    """在控件树里找到第一个 IconButton。"""

    stack = [control]
    while stack:
        node = stack.pop()
        if isinstance(node, ft.IconButton):
            return node
        content = getattr(node, "content", None)
        if content is not None:
            stack.append(content)
        controls = getattr(node, "controls", None)
        if controls:
            stack.extend(controls)
    raise AssertionError("未找到 IconButton")


# —— DashboardView ————————————————————————————————————————————


def _mounted_dashboard(
    state: AppState, bridge: object | None = None
) -> tuple[DashboardView, _FakePage]:
    """构造并模拟挂载仪表盘，返回 (view, fake_page)。"""

    ctx = ViewContext(state=state, bridge=bridge)
    view = DashboardView(ctx)
    page = _FakePage()
    view.page = page  # type: ignore[assignment]
    view.did_mount()
    return view, page


def test_dashboard_connection_reflects_active_platform() -> None:
    """连接状态卡随激活平台状态刷新"""
    state = AppState()
    view, _page = _mounted_dashboard(state)

    state.platforms.replace(
        [
            PlatformStatusVM(
                "vtube_studio",
                "VTube Studio",
                ConnectionState.CONNECTED,
                endpoint="ws://127.0.0.1:8001",
                model_name="Hiyori",
            )
        ]
    )
    state.active_platform_id.set("vtube_studio")

    assert view._conn_state.value == "已连接"
    assert view._conn_endpoint.value == "ws://127.0.0.1:8001"
    assert view._conn_model.value == "模型: Hiyori"
    view.will_unmount()


def test_dashboard_audio_meter_follows_state() -> None:
    """音频电平卡随 audio_level 刷新"""
    state = AppState()
    view, _page = _mounted_dashboard(state)
    state.audio_level.set(
        AudioLevelVM(rms=0.3, peak=0.6, source=AudioSourceKind.TTS, active=True)
    )
    assert view._audio_meter._rms_bar.value == 0.3
    assert view._audio_meter._source_text.value == "源: TTS"
    view.will_unmount()


def test_dashboard_controllers_and_expressions_render() -> None:
    """控制器区只展示 idle 型（过滤 oneshot），表情区随状态渲染，空态显示提示"""
    state = AppState()
    view, _page = _mounted_dashboard(state)

    # 初始空态
    assert len(view._controllers_wrap.controls) == 1  # 占位提示
    assert len(view._expressions_wrap.controls) == 1

    state.controllers.replace(
        [
            ControllerVM(
                key="blink",
                display_name="眨眼",
                type="idle",
                state=ControllerState.RUNNING,
            ),
            ControllerVM(
                key="breathing",
                display_name="呼吸",
                type="idle",
                state=ControllerState.RUNNING,
            ),
            # oneshot 表情解算应被过滤，不出现在控制器区
            ControllerVM(
                key="expression",
                display_name="表情解算",
                type="oneshot",
                state=ControllerState.STOPPED,
            ),
        ]
    )
    state.expressions.replace(
        [
            ExpressionVM(key="joy", display_name="喜悦", emoji="😊"),
            ExpressionVM(key="anger", display_name="愤怒", emoji="😠"),
        ]
    )
    assert (
        len(view._controllers_wrap.controls) == 2
    )  # 仅 blink + breathing，expression 被过滤
    assert len(view._expressions_wrap.controls) == 2
    view.will_unmount()


def test_dashboard_controllers_only_oneshot_shows_empty_hint() -> None:
    """控制器全是 oneshot 时，过滤后为空，显示占位提示"""
    state = AppState()
    view, _page = _mounted_dashboard(state)
    state.controllers.replace(
        [
            ControllerVM(
                key="expression",
                display_name="表情解算",
                type="oneshot",
                state=ControllerState.STOPPED,
            )
        ]
    )
    assert len(view._controllers_wrap.controls) == 1
    assert isinstance(view._controllers_wrap.controls[0], ft.Text)
    view.will_unmount()


async def test_dashboard_toggle_controller_dispatches_intent() -> None:
    """点击 idle 控制器按钮 -> 经 run_task 调度 set_controller_enabled"""
    state = AppState()
    adapter = _FakeAdapter()
    view, page = _mounted_dashboard(state, bridge=_FakeBridge(adapter))
    state.active_platform_id.set("vtube_studio")
    state.controllers.replace(
        [
            ControllerVM(
                key="blink",
                display_name="眨眼",
                type="idle",
                state=ControllerState.RUNNING,
            )
        ]
    )

    card_container = view._controllers_wrap.controls[0]
    button = _find_icon_button(card_container)
    _click(button)  # 运行中 -> 请求停止

    assert len(page.tasks) == 1
    await page.tasks[0]()  # 执行被调度的协程
    assert adapter.toggled == [("blink", False)]
    view.will_unmount()


async def test_dashboard_trigger_expression_dispatches_intent() -> None:
    """点击快速表情按钮 -> 经 run_task 调度 trigger_expression"""
    state = AppState()
    adapter = _FakeAdapter()
    view, page = _mounted_dashboard(state, bridge=_FakeBridge(adapter))
    state.active_platform_id.set("vtube_studio")
    state.expressions.replace(
        [ExpressionVM(key="joy", display_name="喜悦", emoji="😊")]
    )

    button = view._expressions_wrap.controls[0]
    _click(button)

    assert len(page.tasks) == 1
    await page.tasks[0]()
    assert adapter.triggered == ["joy"]
    view.will_unmount()


def test_dashboard_intent_without_bridge_is_noop() -> None:
    """无 bridge 时点击不抛异常、不调度任务"""
    state = AppState()
    view, page = _mounted_dashboard(state, bridge=None)
    state.expressions.replace(
        [ExpressionVM(key="joy", display_name="喜悦", emoji="😊")]
    )
    _click(view._expressions_wrap.controls[0])
    assert page.tasks == []
    view.will_unmount()

"""测试 GUI 通用框架层（P0/P1）

覆盖：
- Observable / ObservableList 的通知、去抖、容量裁剪、就地通知与退订
- AppState 平台查找
- theme 着色函数 / registry 注册表 / async_bridge 跨线程调度 / fonts 字体落地
- view-model 默认值与派生属性
- AppShell 懒加载构造 5 个视图、路由切换与导航高亮
- 视图 did_mount/will_unmount 的订阅生命周期（不接真实 page）
- 顶栏状态订阅随平台 / 音频状态更新

注：这些用例只验证纯 Python 逻辑与控件树装配，不渲染真实 Flet 窗口。
"""

from __future__ import annotations

from livestudio.gui.core.app_state import AppState
from livestudio.gui.core.async_bridge import AsyncBridge
from livestudio.gui.core.fonts import APP_FONT_ASSET_PATH, ASSETS_DIR, ensure_app_font
from livestudio.gui.core.observable import Observable, ObservableList
from livestudio.gui.core.registry import PlatformRegistry
from livestudio.gui.core.theme import (
    PALETTE,
    connection_color,
    controller_color,
    level_color,
)
from livestudio.gui.core.view_context import ViewContext
from livestudio.gui.core.view_models import (
    AudioLevelVM,
    AudioSourceKind,
    ConnectionState,
    ControllerState,
    ControllerVM,
    DiscoveredEndpointVM,
    LogEntryVM,
    PlatformDescriptor,
    PlatformStatusVM,
)
from livestudio.gui.views.shell import NAV_ITEMS, AppShell


def test_observable_notify_dedup_and_unsubscribe() -> None:
    """订阅立即触发、等值去抖、退订后不再通知"""
    seen: list[int] = []
    observable = Observable(0)
    unsubscribe = observable.subscribe(seen.append, immediate=True)
    observable.set(1)
    observable.set(1)  # 等值不触发
    observable.set(2)
    unsubscribe()
    observable.set(3)  # 已退订
    assert seen == [0, 1, 2]


def test_observable_list_cap_trims_to_tail() -> None:
    """ObservableList 指定 cap 时保留末尾若干条"""
    items: ObservableList[int] = ObservableList()
    snapshots: list[list[int]] = []
    items.subscribe(lambda value: snapshots.append(list(value)), immediate=False)
    items.append(1)
    items.append(2, cap=1)
    assert items.value == [2]
    assert snapshots[-1] == [2]


def test_shell_lazily_builds_all_views_and_wires_navigate() -> None:
    """AppShell 能为 5 个入口懒加载视图，并把 navigate 装配进上下文"""
    state = AppState()
    ctx = ViewContext(state=state)
    shell = AppShell(ctx)

    for item in NAV_ITEMS:
        ctx.navigate(item.route)
        assert shell._views.get(item.route) is not None

    assert len(shell._views) == len(NAV_ITEMS)
    assert ctx.navigate == shell.navigate  # 绑定方法用 == 比较


def test_view_mount_lifecycle_subscribes_and_cleans_up() -> None:
    """视图挂载建立订阅、卸载后订阅句柄清空，状态推送不抛异常"""
    state = AppState()
    ctx = ViewContext(state=state)
    shell = AppShell(ctx)
    for item in NAV_ITEMS:
        ctx.navigate(item.route)

    for item in NAV_ITEMS:
        view = shell._views[item.route]
        view.did_mount()
        state.platforms.replace(
            [PlatformStatusVM("vtube_studio", "VTube Studio", ConnectionState.CONNECTED, model_name="Hiyori")]
        )
        state.active_platform_id.set("vtube_studio")
        state.audio_level.set(AudioLevelVM(rms=0.5, peak=0.8, active=True))
        state.logs.append(LogEntryVM(ts="12:00:00.000", level="INFO", message="hello", color="#000"))
        view.will_unmount()
        assert view._unsubs == []


def test_shell_topbar_reflects_platform_and_audio_state() -> None:
    """顶栏订阅平台与音频状态并更新文本"""
    state = AppState()
    ctx = ViewContext(state=state)
    shell = AppShell(ctx)
    shell.did_mount()

    state.platforms.replace([PlatformStatusVM("vtube_studio", "VTube Studio", ConnectionState.CONNECTED, model_name="Hiyori")])
    state.active_platform_id.set("vtube_studio")
    assert "VTube Studio" in shell._status_text.value
    assert "Hiyori" in shell._status_text.value

    state.audio_level.set(AudioLevelVM(active=True, source=AudioSourceKind.MICROPHONE))
    assert shell._audio_text.value == "麦克风"

    shell.will_unmount()


# —— Observable 其余语义 ——————————————————————————————————————


def test_observable_update_applies_mutator() -> None:
    """update() 基于旧值计算新值并写入"""
    observable: Observable[int] = Observable(10)
    observable.update(lambda old: old + 5)
    assert observable.value == 15


def test_observable_notify_forces_emit_without_value_change() -> None:
    """notify() 在值未变时也强制通知一次（就地修改可变值场景）"""
    seen: list[int] = []
    observable: Observable[int] = Observable(1)
    observable.subscribe(seen.append, immediate=False)
    observable.notify()
    observable.notify()
    assert seen == [1, 1]


def test_observable_callback_can_unsubscribe_during_emit() -> None:
    """通知遍历副本，允许回调内部退订而不影响本轮其它订阅者"""
    observable: Observable[int] = Observable(0)
    received_b: list[int] = []
    unsub_a = None

    def listener_a(_value: int) -> None:
        if unsub_a is not None:
            unsub_a()  # 在通知过程中退订自己

    unsub_a = observable.subscribe(listener_a, immediate=False)
    observable.subscribe(received_b.append, immediate=False)
    observable.set(1)  # listener_a 退订自身，listener_b 仍应收到
    assert received_b == [1]


def test_observable_list_extend_replace_clear() -> None:
    """ObservableList 的 extend / replace / clear 行为"""
    items: ObservableList[int] = ObservableList([1])
    items.extend([2, 3])
    assert items.value == [1, 2, 3]
    items.extend([4, 5, 6], cap=2)  # 超出容量保留末尾
    assert items.value == [5, 6]
    items.replace([9])
    assert items.value == [9]
    items.clear()
    assert items.value == []


# —— AppState 平台查找 ——————————————————————————————————————


def test_app_state_platform_lookup() -> None:
    """platform_status 按 id 命中；active_platform_status 跟随激活 id"""
    state = AppState()
    state.platforms.replace(
        [
            PlatformStatusVM("vtube_studio", "VTube Studio"),
            PlatformStatusVM("other", "Other"),
        ]
    )
    assert state.platform_status("other").display_name == "Other"
    assert state.platform_status("missing") is None
    assert state.active_platform_status() is None  # 尚未指定激活平台
    state.active_platform_id.set("vtube_studio")
    assert state.active_platform_status().platform_id == "vtube_studio"


# —— theme 着色函数 ——————————————————————————————————————————


def test_theme_color_helpers_map_states() -> None:
    """连接 / 控制器 / 日志级别映射到预期语义色"""
    assert connection_color(ConnectionState.CONNECTED) == PALETTE.success
    assert connection_color(ConnectionState.CONNECTING) == PALETTE.warning
    assert connection_color(ConnectionState.ERROR) == PALETTE.danger
    assert connection_color(ConnectionState.DISCONNECTED) == PALETTE.text_muted

    assert controller_color(ControllerState.RUNNING) == PALETTE.success
    assert controller_color(ControllerState.STOPPED) == PALETTE.text_muted
    assert controller_color(ControllerState.ERROR) == PALETTE.danger

    assert level_color("WARNING") == PALETTE.warning
    assert level_color("error") == PALETTE.danger  # 大小写不敏感
    assert level_color("UNKNOWN") == PALETTE.text  # 兜底


# —— registry 注册表 ——————————————————————————————————————————


def _dummy_factory(*_args, **_kwargs) -> None:
    """注册表测试用的占位工厂。"""


def test_platform_registry_register_get_and_order() -> None:
    """注册表按序返回、按 id 取用、重复 id 覆盖"""
    registry = PlatformRegistry()
    assert len(registry) == 0
    assert "vtube_studio" not in registry

    desc = PlatformDescriptor(
        id="vtube_studio",
        display_name="VTube Studio",
        icon="hub",
        adapter_factory=_dummy_factory,
        panel_factory=_dummy_factory,
    )
    registry.register(desc)
    assert len(registry) == 1
    assert "vtube_studio" in registry
    assert registry.get("vtube_studio") is desc
    assert registry.get("missing") is None
    assert [d.id for d in registry.all()] == ["vtube_studio"]

    # 同 id 覆盖
    desc2 = PlatformDescriptor("vtube_studio", "VTS v2", "hub", _dummy_factory, _dummy_factory)
    registry.register(desc2)
    assert len(registry) == 1
    assert registry.get("vtube_studio").display_name == "VTS v2"


# —— async_bridge 跨线程调度 ——————————————————————————————————


class _FakeLoop:
    """记录 call_soon_threadsafe 调用的假事件循环。"""

    def __init__(self) -> None:
        self.scheduled: list = []

    def call_soon_threadsafe(self, fn, *args) -> None:
        self.scheduled.append(fn)
        fn(*args)  # 立即执行，便于断言副作用


class _FakePage:
    def __init__(self) -> None:
        self.updated = 0

    def update(self, *controls) -> None:  # noqa: ARG002
        self.updated += 1


def test_async_bridge_posts_through_loop() -> None:
    """post 经 call_soon_threadsafe 调度；post_update 触发 page.update；bind_loop 可替换循环"""
    page = _FakePage()
    loop = _FakeLoop()
    bridge = AsyncBridge(page, loop=loop)

    flag: list[str] = []
    bridge.post(lambda: flag.append("x"))
    assert flag == ["x"]
    assert len(loop.scheduled) == 1

    bridge.post_update()
    assert page.updated == 1

    loop2 = _FakeLoop()
    bridge.bind_loop(loop2)
    bridge.post(lambda: None)
    assert len(loop2.scheduled) == 1


# —— view-model 默认值与派生属性 ————————————————————————————————


def test_view_model_defaults_and_derived() -> None:
    """关键 view-model 的默认值与派生属性"""
    status = PlatformStatusVM("vtube_studio", "VTube Studio")
    assert status.connection is ConnectionState.DISCONNECTED
    assert status.model_name == ""

    endpoint = DiscoveredEndpointVM(name="VTS", host="192.168.1.20", port=8001)
    assert endpoint.address == "ws://192.168.1.20:8001"

    controller = ControllerVM(key="blink", display_name="眨眼")
    assert controller.type == "idle"
    assert controller.state is ControllerState.STOPPED
    assert controller.enabled is True

    level = AudioLevelVM()
    assert level.active is False
    assert level.source is AudioSourceKind.MICROPHONE


# —— 导航切换与高亮 ——————————————————————————————————————————


def test_shell_navigation_switches_content_and_rail_index() -> None:
    """navigate 切换内容视图并同步 NavigationRail 选中项；非法路由忽略"""
    state = AppState()
    ctx = ViewContext(state=state)
    shell = AppShell(ctx)

    # 初始定位到第一个入口（dashboard）
    assert shell._rail.selected_index == 0
    assert shell._content.content is shell._views["dashboard"]

    shell.navigate("logs")
    logs_index = next(i for i, item in enumerate(NAV_ITEMS) if item.route == "logs")
    assert shell._rail.selected_index == logs_index
    assert shell._content.content is shell._views["logs"]

    # 非法路由不改变当前状态
    shell.navigate("does_not_exist")
    assert shell._rail.selected_index == logs_index


def test_shell_caches_view_instances_across_navigation() -> None:
    """重复导航到同一路由复用同一视图实例（缓存）"""
    state = AppState()
    ctx = ViewContext(state=state)
    shell = AppShell(ctx)

    shell.navigate("audio")
    first = shell._views["audio"]
    shell.navigate("dashboard")
    shell.navigate("audio")
    assert shell._views["audio"] is first


def test_logs_view_renders_entries_into_listview() -> None:
    """日志视图订阅 AppState.logs 并把记录渲染进 ListView"""
    state = AppState()
    ctx = ViewContext(state=state)
    shell = AppShell(ctx)
    shell.navigate("logs")
    logs_view = shell._views["logs"]
    logs_view.did_mount()  # 建立订阅（空列表 -> 显示占位）

    state.logs.append(LogEntryVM(ts="12:00:00.000", level="INFO", message="hello", color=PALETTE.text))
    assert len(logs_view._list.controls) == 1
    assert logs_view._body.content is logs_view._list

    logs_view.will_unmount()
    assert logs_view._unsubs == []


# —— fonts 字体落地 ——————————————————————————————————————————


def test_ensure_app_font_lands_a_usable_file() -> None:
    """ensure_app_font 返回相对注册路径，且 assets 中存在非空字体文件"""
    result = ensure_app_font()
    # 测试机若无任何候选系统字体则返回 None（跳过断言落地），但路径常量始终有效
    assert APP_FONT_ASSET_PATH.endswith(".ttf")
    if result is not None:
        assert result == APP_FONT_ASSET_PATH
        target = ASSETS_DIR / result
        assert target.exists()
        assert target.stat().st_size > 0

"""测试 P5 音频流页与日志页

覆盖：
- AudioView：电平订阅、单选切草稿、切换按钮态机、后端确认后回归
- AudioView：无 bridge 时点击安全降级
- LogsView：渲染、级别过滤（最低优先级阈值）、关键字过滤、暂停/继续、清空、自动滚动开关

注：用假 page 复刻 page.run_task 的 iscoroutinefunction 断言，避免再次出现
P3 阶段那次"测试通过但运行时 AssertionError"的保真度漏洞。
"""

from __future__ import annotations

import asyncio

import flet as ft

from livestudio.gui.core.app_state import AppState
from livestudio.gui.core.view_context import ViewContext
from livestudio.gui.core.view_models import AudioLevelVM, AudioSourceKind, LogEntryVM
from livestudio.gui.views.audio import AudioView
from livestudio.gui.views.logs import LogsView


class _FakePage:
    """假 page：复刻 run_task 的协程函数断言。"""

    def __init__(self) -> None:
        self.tasks: list = []

    def run_task(self, handler) -> None:
        assert asyncio.iscoroutinefunction(handler), "run_task 需要协程函数"
        self.tasks.append(handler)

    def update(self, *controls) -> None:  # noqa: ARG002
        pass


class _FakeBridge:
    """假桥接：记录音频源切换调用。"""

    def __init__(self) -> None:
        self.switched: list = []

    async def switch_audio_source(self, kind: AudioSourceKind) -> None:
        self.switched.append(kind)


class _Ctl:
    """构造 on_change 事件：e.control.value。"""

    def __init__(self, value) -> None:
        self.value = value


class _Ev:
    def __init__(self, value) -> None:
        self.control = _Ctl(value)


def _mount_audio(state: AppState, bridge: object | None) -> tuple[AudioView, _FakePage]:
    view = AudioView(ViewContext(state=state, bridge=bridge))
    page = _FakePage()
    view.page = page  # type: ignore[assignment]
    view.did_mount()
    return view, page


def _mount_logs(state: AppState) -> tuple[LogsView, _FakePage]:
    view = LogsView(ViewContext(state=state))
    page = _FakePage()
    view.page = page  # type: ignore[assignment]
    view.did_mount()
    return view, page


# —— AudioView ——————————————————————————————————————————————


def test_audio_view_meter_follows_state() -> None:
    """实时电平卡随 state.audio_level 刷新"""
    state = AppState()
    view, _page = _mount_audio(state, _FakeBridge())
    state.audio_level.set(AudioLevelVM(rms=0.6, peak=0.8, source=AudioSourceKind.TTS, active=True))
    assert view._audio_meter._rms_bar.value == 0.6
    assert view._audio_meter._source_text.value == "源: TTS"


def test_audio_view_switch_button_disabled_when_draft_equals_active() -> None:
    """草稿与当前源相同时按钮禁用并提示"""
    state = AppState()
    view, _page = _mount_audio(state, _FakeBridge())
    # 默认 draft=MIC，state=MIC
    assert view._switch_button.disabled is True
    assert view._switch_button.text == "已是当前源"


def test_audio_view_radio_change_enables_switch_button() -> None:
    """改 radio 草稿后按钮启用且文案恢复"""
    state = AppState()
    view, _page = _mount_audio(state, _FakeBridge())
    view._on_radio_change(_Ev("tts"))
    assert view._draft == AudioSourceKind.TTS
    assert view._switch_button.disabled is False
    assert view._switch_button.text == "切换为选中源"


async def test_audio_view_click_switch_dispatches_intent_and_locks_button() -> None:
    """点击切换：按钮锁定为'切换中…'，意图经 run_task 转发到 bridge"""
    state = AppState()
    bridge = _FakeBridge()
    view, page = _mount_audio(state, bridge)
    view._on_radio_change(_Ev("tts"))
    view._on_switch_click(None)
    assert view._switching is True
    assert view._switch_button.disabled is True
    assert view._switch_button.text == "切换中…"
    assert len(page.tasks) == 1
    await page.tasks[0]()
    assert bridge.switched == [AudioSourceKind.TTS]


def test_audio_view_backend_confirm_releases_button() -> None:
    """后端确认（state.audio_source 变更）后按钮恢复，提示更新"""
    state = AppState()
    view, _page = _mount_audio(state, _FakeBridge())
    view._on_radio_change(_Ev("tts"))
    view._on_switch_click(None)
    state.audio_source.set(AudioSourceKind.TTS)  # 模拟后端确认
    assert view._switching is False
    assert view._switch_button.disabled is True  # draft == active
    assert view._switch_button.text == "已是当前源"
    assert view._active_hint.value == "当前: TTS"


def test_audio_view_click_without_bridge_is_noop() -> None:
    """无 bridge 时点击切换不抛异常、不调度任务"""
    state = AppState()
    view, page = _mount_audio(state, bridge=None)
    view._on_radio_change(_Ev("tts"))
    view._on_switch_click(None)
    assert page.tasks == []


def test_audio_view_repeated_click_during_switching_is_ignored() -> None:
    """切换中再次点击不重复调度"""
    state = AppState()
    bridge = _FakeBridge()
    view, page = _mount_audio(state, bridge)
    view._on_radio_change(_Ev("tts"))
    view._on_switch_click(None)
    view._on_switch_click(None)  # 第二次应被忽略
    assert len(page.tasks) == 1


# —— LogsView ——————————————————————————————————————————————


def _entry(level: str, message: str) -> LogEntryVM:
    return LogEntryVM(ts="12:00:00.000", level=level, message=message, color="#000")


def test_logs_view_renders_all_entries() -> None:
    """无过滤时渲染全部条目"""
    state = AppState()
    view, _page = _mount_logs(state)
    state.logs.replace([_entry("INFO", "a"), _entry("WARNING", "b"), _entry("ERROR", "c")])
    assert len(view._list.controls) == 3


def test_logs_view_level_filter_uses_priority_threshold() -> None:
    """级别过滤按优先级最低阈值（>= 选中级别）筛选"""
    state = AppState()
    view, _page = _mount_logs(state)
    state.logs.replace(
        [_entry("DEBUG", "d"), _entry("INFO", "i"), _entry("WARNING", "w"), _entry("ERROR", "e")],
    )
    view._on_level_change(_Ev("WARNING"))
    # WARNING 与 ERROR 通过，DEBUG / INFO 被过滤
    assert len(view._list.controls) == 2


def test_logs_view_keyword_filter_matches_message_only() -> None:
    """关键字仅匹配 message，区分大小写不敏感"""
    state = AppState()
    view, _page = _mount_logs(state)
    state.logs.replace([_entry("INFO", "Hello world"), _entry("INFO", "goodbye")])
    view._on_keyword_change(_Ev("hello"))
    assert len(view._list.controls) == 1


def test_logs_view_pause_blocks_updates_and_resume_replays() -> None:
    """暂停后新日志不刷新视图；继续时立即拉最新"""
    state = AppState()
    view, _page = _mount_logs(state)
    state.logs.replace([_entry("INFO", "a")])
    view._on_pause_click(None)  # 进入暂停
    assert view._paused is True
    state.logs.append(_entry("INFO", "b"))  # 暂停期间写入
    assert len(view._list.controls) == 1  # 视图未追加
    view._on_pause_click(None)  # 继续
    assert view._paused is False
    assert len(view._list.controls) == 2  # 拉到最新


def test_logs_view_clear_empties_view_but_keeps_state_buffer() -> None:
    """清空仅清当前视图，state.logs 缓冲不动"""
    state = AppState()
    view, _page = _mount_logs(state)
    state.logs.replace([_entry("INFO", "a"), _entry("INFO", "b")])
    assert len(view._list.controls) == 2
    view._on_clear_click(None)
    assert len(view._list.controls) == 0
    assert len(state.logs.value) == 2  # 状态缓冲保留


def test_logs_view_auto_scroll_switch_propagates_to_listview() -> None:
    """自动滚动开关同步到 ListView.auto_scroll"""
    state = AppState()
    view, _page = _mount_logs(state)
    assert view._list.auto_scroll is True
    view._on_auto_scroll_change(_Ev(False))
    assert view._auto_scroll is False
    assert view._list.auto_scroll is False


def test_logs_view_pause_button_icon_toggles() -> None:
    """暂停按钮图标在 PAUSE/PLAY_ARROW 间切换"""
    state = AppState()
    view, _page = _mount_logs(state)
    assert view._pause_button.icon == ft.Icons.PAUSE
    view._on_pause_click(None)
    assert view._pause_button.icon == ft.Icons.PLAY_ARROW
    view._on_pause_click(None)
    assert view._pause_button.icon == ft.Icons.PAUSE

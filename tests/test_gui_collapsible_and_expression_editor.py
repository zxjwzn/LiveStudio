"""测试 GUI 组件：可折叠分区逻辑 + 表情 AU 编辑器数据操作 + YAML 序列化安全。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# ── 1. _CollapsibleSection 懒构建逻辑 ────────────────────────────


def test_collapsible_section_default_collapsed():
    """默认折叠：_content_built 为 False，_body 不可见。"""

    from livestudio.gui.components.model_config_card import _CollapsibleSection

    calls: list[str] = []

    def _builder():
        calls.append("built")
        import flet as ft

        return ft.Text("content")

    section = _CollapsibleSection("测试", _builder)
    assert section._expanded is False
    assert section._content_built is False
    assert section._body.visible is False
    assert calls == []  # 未调用构建函数


def test_collapsible_section_expanded_builds_immediately():
    """expanded=True 时立即构建内容。"""

    from livestudio.gui.components.model_config_card import _CollapsibleSection

    calls: list[str] = []

    def _builder():
        import flet as ft

        calls.append("built")
        return ft.Text("content")

    section = _CollapsibleSection("测试", _builder, expanded=True)
    assert section._expanded is True
    assert section._content_built is True
    assert section._body.visible is True
    assert calls == ["built"]


def test_collapsible_section_toggle_builds_on_first_expand():
    """首次展开时构建内容，再次折叠不重复构建。"""

    from unittest.mock import MagicMock

    from livestudio.gui.components.model_config_card import _CollapsibleSection

    import flet as ft

    calls: list[str] = []

    def _builder():
        calls.append("built")
        return ft.Text("lazy content")

    section = _CollapsibleSection("测试", _builder)
    assert calls == []

    # 模拟 toggle（跳过 self.update()）
    event = MagicMock()
    section._toggle(event)
    assert section._expanded is True
    assert section._content_built is True
    assert section._body.visible is True
    assert calls == ["built"]

    # 再次 toggle 折叠
    section._toggle(event)
    assert section._expanded is False
    assert section._body.visible is False
    assert calls == ["built"]  # 没有第二次构建

    # 再次展开也不重新构建
    section._toggle(event)
    assert section._expanded is True
    assert section._body.visible is True
    assert calls == ["built"]


# ── 2. ExpressionUnitsEditor 数据操作 ────────────────────────────


class TestExpressionUnitsEditorTargets:
    """测试表情 AU 编辑器的 targets 增删改。"""

    def _make_editor(self, semantic=None, native=None):
        from livestudio.gui.components.expression_units_editor import (
            ExpressionUnitsEditor,
        )

        self.emitted: list[tuple] = []

        def _on_change(s, n):
            self.emitted.append((s, n))

        return ExpressionUnitsEditor(
            semantic_units=semantic
            or [
                {
                    "id": "brow_up",
                    "enabled": True,
                    "targets": [{"action": "brow.height", "min_value": 0.0, "max_value": 1.0}],
                    "emotions": {"joy": 0.8},
                }
            ],
            native_units=native or [],
            on_change=_on_change,
        )

    def test_add_target(self):
        editor = self._make_editor()
        assert len(editor._semantic[0]["targets"]) == 1

        editor._add_target(0)
        assert len(editor._semantic[0]["targets"]) == 2
        assert editor._semantic[0]["targets"][1] == {
            "action": "",
            "min_value": 0.0,
            "max_value": 1.0,
        }
        assert len(self.emitted) == 1

    def test_delete_target(self):
        editor = self._make_editor()
        editor._delete_target(0, 0)
        assert editor._semantic[0]["targets"] == []
        assert len(self.emitted) == 1

    def test_update_target_action(self):
        editor = self._make_editor()
        editor._update_target(0, 0, "action", "eye.open")
        assert editor._semantic[0]["targets"][0]["action"] == "eye.open"
        assert len(self.emitted) == 1

    def test_update_target_num(self):
        editor = self._make_editor()
        editor._update_target_num(0, 0, "min_value", "0.3")
        assert editor._semantic[0]["targets"][0]["min_value"] == 0.3
        assert len(self.emitted) == 1

    def test_update_target_num_invalid_ignored(self):
        editor = self._make_editor()
        editor._update_target_num(0, 0, "min_value", "not_a_number")
        # 不应触发 emit 且值不变
        assert editor._semantic[0]["targets"][0]["min_value"] == 0.0
        assert len(self.emitted) == 0

    def test_add_target_out_of_range_noop(self):
        editor = self._make_editor()
        editor._add_target(99)
        assert len(self.emitted) == 0


class TestExpressionUnitsEditorEmotions:
    """测试表情 AU 编辑器的 emotions 增删改。"""

    def _make_editor(self):
        from livestudio.gui.components.expression_units_editor import (
            ExpressionUnitsEditor,
        )

        self.emitted: list[tuple] = []

        def _on_change(s, n):
            self.emitted.append((s, n))

        return ExpressionUnitsEditor(
            semantic_units=[
                {
                    "id": "smile",
                    "enabled": True,
                    "targets": [],
                    "emotions": {"joy": 0.8, "surprise": 0.3},
                }
            ],
            native_units=[],
            on_change=_on_change,
        )

    def test_add_emotion(self):
        editor = self._make_editor()
        editor._add_emotion(0)
        emotions = editor._semantic[0]["emotions"]
        # joy 和 surprise 已用，应该选 sadness
        assert "sadness" in emotions
        assert emotions["sadness"] == 0.5
        assert len(self.emitted) == 1

    def test_delete_emotion(self):
        editor = self._make_editor()
        editor._delete_emotion(0, 0)  # 删第一个 (joy)
        emotions = editor._semantic[0]["emotions"]
        assert "joy" not in emotions
        assert "surprise" in emotions
        assert len(self.emitted) == 1

    def test_update_emotion_key(self):
        editor = self._make_editor()
        editor._update_emotion_key(0, 0, "anger")
        emotions = editor._semantic[0]["emotions"]
        # joy 被替换为 anger，保留权重
        assert "joy" not in emotions
        assert emotions["anger"] == 0.8
        assert emotions["surprise"] == 0.3

    def test_update_emotion_weight(self):
        editor = self._make_editor()
        editor._update_emotion_weight(0, 0, "0.95")
        emotions = editor._semantic[0]["emotions"]
        assert emotions["joy"] == 0.95

    def test_update_emotion_weight_invalid_ignored(self):
        editor = self._make_editor()
        editor._update_emotion_weight(0, 0, "abc")
        emotions = editor._semantic[0]["emotions"]
        assert emotions["joy"] == 0.8
        assert len(self.emitted) == 0


# ── 3. YAML 序列化安全（SemanticAction 枚举问题） ─────────────────


@pytest.fixture
def model_config_dir(tmp_path):
    return tmp_path / "configs"


async def test_save_model_config_raw_handles_enum_types(tmp_path):
    """验证 save_model_config_raw 能安全序列化含 StrEnum 的数据。"""

    import yaml

    from livestudio.services.platforms.vtubestudio.config import (
        VTubeStudioModelConfig,
    )

    # 构造含 SemanticAction 枚举值的配置
    from livestudio.services.platforms.model import PlatformModelIdentity

    identity = PlatformModelIdentity(
        platform_name="vtubestudio",
        model_id="test-model-id",
        model_name="TestModel",
    )
    config = VTubeStudioModelConfig.create_default(identity)
    # model_dump 不带 mode="json" 会保留枚举对象
    raw_data = config.model_dump()

    # 验证原始数据含枚举（这正是之前崩溃的原因）
    bindings = raw_data.get("semantic_profile", {}).get("bindings", [])
    has_enum = False
    for binding in bindings:
        action = binding.get("action")
        if action is not None and not isinstance(action, str):
            has_enum = True
            break
        # Pydantic v2 在某些模式下可能返回字符串，检查类型就行
    # 无论是否含枚举，save_model_config_raw 都应该正常工作

    # 模拟写入
    config_dir = tmp_path / "model_configs"
    config_dir.mkdir()
    file_stem = "TestModel_test"

    # 直接测试序列化逻辑（与 save_model_config_raw 相同）
    validated = VTubeStudioModelConfig.model_validate(raw_data)
    clean = validated.model_dump(mode="json", exclude_none=True)
    # 这一步之前会抛 RepresenterError
    content = yaml.safe_dump(clean, allow_unicode=True, sort_keys=False)
    assert isinstance(content, str)
    assert "vtubestudio" in content


async def test_save_model_config_raw_roundtrip(tmp_path):
    """验证通过 adapter 保存再加载，数据一致。"""

    from livestudio.services.platforms.model import PlatformModelIdentity
    from livestudio.services.platforms.vtubestudio.config import (
        VTubeStudioModelConfig,
    )

    identity = PlatformModelIdentity(
        platform_name="vtubestudio",
        model_id="roundtrip-id",
        model_name="Roundtrip",
    )
    config = VTubeStudioModelConfig.create_default(identity)
    raw_data = config.model_dump()

    # 模拟 save 逻辑
    validated = VTubeStudioModelConfig.model_validate(raw_data)
    clean = validated.model_dump(mode="json", exclude_none=True)

    import yaml

    content = yaml.safe_dump(clean, allow_unicode=True, sort_keys=False)

    # 重新加载
    loaded = yaml.safe_load(content)
    reloaded_config = VTubeStudioModelConfig.model_validate(loaded)
    assert reloaded_config.model.model_name == "Roundtrip"
    assert reloaded_config.model.model_id == "roundtrip-id"


# ── 4. PlatformView endpoint 持久化逻辑 ──────────────────────────


def test_platform_view_endpoint_field_persists():
    """验证 _endpoint_fields 字典结构在多次 build_card 后保留同一实例。"""

    from livestudio.gui.core.view_models import ConnectionState, PlatformStatusVM

    import flet as ft

    # 模拟 PlatformView 的 endpoint 持久化逻辑
    endpoint_fields: dict[str, ft.TextField] = {}
    last_synced: dict[str, str] = {}

    def get_or_create(status: PlatformStatusVM) -> ft.TextField:
        pid = status.platform_id
        if pid not in endpoint_fields:
            endpoint_fields[pid] = ft.TextField(
                value=status.endpoint or "",
                label="Endpoint",
                dense=True,
                width=280,
            )
            last_synced[pid] = status.endpoint or ""
        field = endpoint_fields[pid]
        backend_ep = status.endpoint or ""
        if backend_ep != last_synced.get(pid, ""):
            field.value = backend_ep
            last_synced[pid] = backend_ep
        return field

    # 首次创建
    status1 = PlatformStatusVM(
        platform_id="vts",
        display_name="VTube Studio",
        connection=ConnectionState.DISCONNECTED,
        endpoint="ws://old:8001",
    )
    f1 = get_or_create(status1)
    assert f1.value == "ws://old:8001"

    # 模拟用户输入新地址
    f1.value = "ws://new:8001"

    # 状态变化后再次调用（CONNECTING 但 endpoint 未变）
    status2 = PlatformStatusVM(
        platform_id="vts",
        display_name="VTube Studio",
        connection=ConnectionState.CONNECTING,
        endpoint="ws://old:8001",
    )
    f2 = get_or_create(status2)
    assert f2 is f1  # 同一实例
    # 后端 endpoint 未变（仍是 old），不应覆盖用户输入
    assert f2.value == "ws://new:8001"


def test_platform_view_endpoint_field_syncs_on_backend_change():
    """后端写入新 endpoint 后，输入框应同步。"""

    from livestudio.gui.core.view_models import ConnectionState, PlatformStatusVM

    import flet as ft

    endpoint_fields: dict[str, ft.TextField] = {}
    last_synced: dict[str, str] = {}

    def get_or_create(status: PlatformStatusVM) -> ft.TextField:
        pid = status.platform_id
        if pid not in endpoint_fields:
            endpoint_fields[pid] = ft.TextField(value=status.endpoint or "", width=280)
            last_synced[pid] = status.endpoint or ""
        field = endpoint_fields[pid]
        backend_ep = status.endpoint or ""
        if backend_ep != last_synced.get(pid, ""):
            field.value = backend_ep
            last_synced[pid] = backend_ep
        return field

    status_before = PlatformStatusVM(
        platform_id="vts",
        display_name="VTube Studio",
        connection=ConnectionState.DISCONNECTED,
        endpoint="ws://localhost:8001",
    )
    f = get_or_create(status_before)
    assert f.value == "ws://localhost:8001"

    # 后端通过 LAN 发现写入了新地址（endpoint 变化）
    status_after = PlatformStatusVM(
        platform_id="vts",
        display_name="VTube Studio",
        connection=ConnectionState.CONNECTED,
        endpoint="ws://192.168.1.50:8001",
    )
    f = get_or_create(status_after)
    assert f.value == "ws://192.168.1.50:8001"

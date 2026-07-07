"""测试 VTube Studio 平台服务能不能正常开始和结束"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from livestudio.app import VTubeStudioApp
from livestudio.clients.vtube_studio.models import ExpressionStateResponse, InputParameterListResponse
from livestudio.config import ConfigManager
from livestudio.services.expression.models import NativeExpressionTrigger
from livestudio.services.platforms.vtubestudio import (
    VTubeStudio,
    VTubeStudioExpressionStateConfig,
    default_vtube_studio_semantic_profile,
)
from livestudio.services.platforms.vtubestudio.defaults import _PLUGIN_PARAMETER_TABLE
from livestudio.services.semantic_actions import (
    DEFAULT_SEMANTIC_ACTION_SPECS,
    PlatformParameterSpec,
    SemanticAction,
    SemanticTweenRequest,
)


class _DisconnectRecorder:
    def __init__(self) -> None:
        self.disconnect_calls = 0

    async def disconnect(self) -> None:
        self.disconnect_calls += 1


class _InputParameterClient:
    def __init__(self, response: InputParameterListResponse | None = None) -> None:
        self.response = response
        self.created_parameters: list[tuple[str, float, float, float]] = []

    async def get_input_parameters(self) -> InputParameterListResponse:
        if self.response is None:
            raise RuntimeError("api failed")
        return self.response

    async def create_parameter(self, request: Any) -> object:
        self.created_parameters.append(
            (
                request.data.parameter_name,
                request.data.min,
                request.data.max,
                request.data.default_value,
            )
        )
        return object()


class _ExpressionClient(_InputParameterClient):
    def __init__(self) -> None:
        super().__init__(_input_parameter_response())
        self.calls: list[tuple[str, bool]] = []

    async def set_expression_active(self, request: Any) -> object:
        self.calls.append((request.data.expression_file, request.data.active))
        return object()

    async def get_expression_state(self, _request: Any) -> ExpressionStateResponse:
        return _expression_state_response()


def _input_parameter_response() -> InputParameterListResponse:
    return InputParameterListResponse.model_validate(
        {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "timestamp": 1,
            "messageType": "InputParameterListResponse",
            "requestID": "test",
            "data": {
                "modelLoaded": True,
                "modelName": "avatar",
                "modelID": "model-1",
                "defaultParameters": [
                    {
                        "name": "MouthOpen",
                        "addedBy": "VTube Studio",
                        "value": 0.0,
                        "min": -2.0,
                        "max": 2.0,
                        "defaultValue": 0.0,
                    },
                    {
                        "name": "CheekPuff",
                        "addedBy": "VTube Studio",
                        "value": 0.0,
                        "min": 0.0,
                        "max": 1.0,
                        "defaultValue": 0.0,
                    },
                    {
                        "name": "TongueOut",
                        "addedBy": "VTube Studio",
                        "value": 0.0,
                        "min": 0.0,
                        "max": 1.0,
                        "defaultValue": 0.0,
                    },
                ],
                "customParameters": [],
            },
        }
    )


def _input_parameter_response_with_plugin_parameters() -> InputParameterListResponse:
    raw = _input_parameter_response().model_dump(by_alias=True)
    raw["data"]["customParameters"] = [
        {
            "name": "MouthFunnel",
            "addedBy": "LiveStudio",
            "value": 0.0,
            "min": 0.0,
            "max": 1.0,
            "defaultValue": 0.0,
        },
        {
            "name": "MouthShrug",
            "addedBy": "LiveStudio",
            "value": 0.0,
            "min": 0.0,
            "max": 1.0,
            "defaultValue": 0.0,
        },
        {
            "name": "JawOpen",
            "addedBy": "LiveStudio",
            "value": 0.0,
            "min": 0.0,
            "max": 1.0,
            "defaultValue": 0.0,
        },
        {
            "name": "MouthPucker",
            "addedBy": "LiveStudio",
            "value": 0.0,
            "min": -1.0,
            "max": 1.0,
            "defaultValue": 0.0,
        },
        {
            "name": "EyeWide",
            "addedBy": "LiveStudio",
            "value": 0.0,
            "min": 0.0,
            "max": 1.0,
            "defaultValue": 0.0,
        },
    ]
    return InputParameterListResponse.model_validate(raw)


def _expression_state_response() -> ExpressionStateResponse:
    return ExpressionStateResponse.model_validate(
        {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "timestamp": 1,
            "messageType": "ExpressionStateResponse",
            "requestID": "test",
            "data": {
                "modelLoaded": True,
                "modelName": "avatar",
                "modelID": "model-1",
                "expressions": [
                    {
                        "name": "1抱枕",
                        "file": "1抱枕.exp3.json",
                        "active": False,
                        "deactivateWhenKeyIsLetGo": False,
                        "autoDeactivateAfterSeconds": False,
                        "secondsRemaining": 0.0,
                        "usedInHotkeys": [],
                        "parameters": [],
                    }
                ],
            },
        }
    )


async def test_vtube_studio_start_disconnects_when_authentication_fails() -> None:
    platform = VTubeStudio()
    client = _DisconnectRecorder()
    platform._client = cast(Any, client)  # noqa: SLF001

    async def connect() -> None:
        pass

    async def authenticate() -> None:
        raise RuntimeError("auth failed")

    platform.connect = connect  # type: ignore[method-assign]
    platform.authenticate = authenticate  # type: ignore[method-assign]

    with patch.object(platform.config_manager, "save", AsyncMock()), pytest.raises(RuntimeError, match="auth failed"):
        await platform.start()

    assert client.disconnect_calls == 1
    assert not platform.is_started
    assert not platform.tween.is_running


async def test_vtube_studio_restart_reconnects_without_destroying_deps() -> None:
    """重启：断开重连但保留依赖（client/model_config_service）。

    区别于 stop——restart 不清空 client，重连成功后服务仍处运行态。验证统一生命
    周期里 restart 的语义：只有 stop 才真正销毁依赖。
    """
    platform = VTubeStudio()
    client = _DisconnectRecorder()
    platform._mark_started()  # noqa: SLF001
    platform._client = cast(Any, client)  # noqa: SLF001

    connect_calls = 0
    authenticate_calls = 0

    async def connect() -> None:
        nonlocal connect_calls
        connect_calls += 1

    async def authenticate() -> None:
        nonlocal authenticate_calls
        authenticate_calls += 1

    platform.connect = connect  # type: ignore[method-assign]
    platform.authenticate = authenticate  # type: ignore[method-assign]

    await platform.restart()

    # 重连发生：旧连接断开一次，随后重新 connect+authenticate
    assert client.disconnect_calls == 1
    assert connect_calls == 1
    assert authenticate_calls == 1
    # 关键：依赖未被销毁，服务仍处运行态
    assert platform.is_started
    assert platform._client is client  # noqa: SLF001
    assert platform.tween.is_running

    await platform.stop()


async def test_reload_model_config_syncs_and_saves_vtube_studio_parameter_specs(
    tmp_path,
) -> None:
    platform = VTubeStudio()
    platform._client = cast(  # noqa: SLF001
        Any,
        _InputParameterClient(_input_parameter_response()),
    )
    platform.config.model_config_dir = str(tmp_path)

    model_config = await platform.reload_model_config("model-1", "avatar")

    mouth_open = next(spec for spec in model_config.parameter_specs if spec.name == "MouthOpen")
    assert mouth_open.minimum == -2.0
    assert mouth_open.maximum == 2.0
    request = platform.semantic_adapter.to_tween_requests(  # type: ignore[union-attr]
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.MOUTH_OPEN.value,
                end_value=1.0,
                duration=0.1,
                easing="linear",
            )
        ]
    )[0]
    assert request.end_value == 2.0

    manager = ConfigManager(type(model_config), platform.model_config_manager.path)
    saved_config = await manager.load()
    saved_mouth_open = next(spec for spec in saved_config.parameter_specs if spec.name == "MouthOpen")
    assert saved_mouth_open.minimum == -2.0
    assert saved_mouth_open.maximum == 2.0


async def test_reload_model_config_creates_plugin_parameters_before_refresh(tmp_path) -> None:
    platform = VTubeStudio()
    client = _InputParameterClient(_input_parameter_response_with_plugin_parameters())
    platform._client = cast(Any, client)  # noqa: SLF001
    platform.config.model_config_dir = str(tmp_path)

    model_config = await platform.reload_model_config("model-1", "avatar")

    assert client.created_parameters == [
        ("EyeWide", 0.0, 1.0, 0.0),
        ("JawOpen", 0.0, 1.0, 0.0),
        ("MouthFunnel", 0.0, 1.0, 0.0),
        ("MouthPucker", -1.0, 1.0, 0.0),
        ("MouthShrug", 0.0, 1.0, 0.0),
    ]
    specs = {spec.name: spec for spec in model_config.parameter_specs}
    assert specs["MouthFunnel"].minimum == 0.0
    assert specs["MouthPucker"].minimum == -1.0
    assert specs["EyeWide"].maximum == 1.0


async def test_reload_model_config_keeps_file_specs_when_vtube_studio_query_fails(
    tmp_path,
) -> None:
    platform = VTubeStudio()
    platform._client = cast(Any, _InputParameterClient())  # noqa: SLF001
    platform.config.model_config_dir = str(tmp_path)

    first_config = await platform.reload_model_config("model-1", "avatar")
    assert first_config.parameter_specs == []

    first_config.parameter_specs = [
        PlatformParameterSpec(
            name="MouthOpen",
            minimum=0.0,
            maximum=1.0,
        )
    ]
    await platform.model_config_manager.save()

    model_config = await platform.reload_model_config("model-1", "avatar")

    assert any(spec.name == "MouthOpen" for spec in model_config.parameter_specs)


async def test_refresh_expression_adapter_uses_latest_expression_config(tmp_path) -> None:
    platform = VTubeStudio()
    client = _ExpressionClient()
    platform._client = cast(Any, client)  # noqa: SLF001
    platform.config.model_config_dir = str(tmp_path)

    model_config = await platform.reload_model_config("model-1", "avatar")
    model_config.expressions.append(VTubeStudioExpressionStateConfig(name="2脸黑", file="2脸黑.exp3.json"))
    platform.refresh_expression_adapter(model_config)

    await platform.apply_native_expressions([NativeExpressionTrigger(platform="vtubestudio", native_ref="2脸黑")])

    assert client.calls == [("2脸黑.exp3.json", True)]


async def test_initial_expression_sync_refreshes_adapter_mapping(tmp_path) -> None:
    platform = VTubeStudio()
    client = _ExpressionClient()
    platform._client = cast(Any, client)  # noqa: SLF001
    platform.config.model_config_dir = str(tmp_path)
    app = object.__new__(VTubeStudioApp)
    app.platform = platform

    model_config = await platform.reload_model_config("model-1", "avatar")
    assert model_config.expressions == []

    await app._sync_native_state(model_config)  # noqa: SLF001
    await platform.apply_native_expressions([NativeExpressionTrigger(platform="vtubestudio", native_ref="1抱枕")])

    assert client.calls == [("1抱枕.exp3.json", True)]


def test_plugin_parameter_semantic_consistency() -> None:
    """插件参数表与语义 spec / 默认绑定三处一致：一对一绑定、范围相等、静息值==默认值。"""

    spec_by_action = {s.id: s for s in DEFAULT_SEMANTIC_ACTION_SPECS}
    profile = default_vtube_studio_semantic_profile()
    bindings = {b.action: b.platform_params for b in profile.bindings}
    for action, plugin_spec in _PLUGIN_PARAMETER_TABLE:
        semantic = spec_by_action[action]
        assert bindings[action] == [plugin_spec.name]
        assert (semantic.minimum, semantic.maximum) == (plugin_spec.minimum, plugin_spec.maximum)
        assert semantic.neutral == plugin_spec.default


async def test_plugin_parameter_pucker_maps_identity_through_adapter(tmp_path) -> None:
    """mouth.pucker 经语义层恒等映射到 MouthPucker=-1.0 的 TweenRequest。"""

    platform = VTubeStudio()
    platform._client = cast(  # noqa: SLF001
        Any,
        _InputParameterClient(_input_parameter_response_with_plugin_parameters()),
    )
    platform.config.model_config_dir = str(tmp_path)

    await platform.reload_model_config("model-1", "avatar")

    request = platform.semantic_adapter.to_tween_requests(  # type: ignore[union-attr]
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.MOUTH_PUCKER.value,
                end_value=-1.0,
                duration=0.1,
                easing="linear",
            )
        ]
    )[0]
    assert request.parameter_name == "MouthPucker"
    assert request.end_value == -1.0


def test_builtin_parameter_semantic_consistency() -> None:
    """VTS 内置参数 CheekPuff / TongueOut 在语义层有对应动作、[0,1] 范围、默认绑定齐全。"""

    spec_by_action = {s.id: s for s in DEFAULT_SEMANTIC_ACTION_SPECS}
    profile = default_vtube_studio_semantic_profile()
    bindings = {b.action: b.platform_params for b in profile.bindings}
    expected = {
        SemanticAction.MOUTH_CHEEK_PUFF: "CheekPuff",
        SemanticAction.MOUTH_TONGUE_OUT: "TongueOut",
    }
    for action, param_name in expected.items():
        semantic = spec_by_action[action]
        assert bindings[action] == [param_name]
        assert (semantic.minimum, semantic.maximum) == (0.0, 1.0)
        assert semantic.neutral == 0.0


async def test_builtin_parameter_tongue_maps_identity_through_adapter(tmp_path) -> None:
    """mouth.tongue.out 经语义层恒等映射到 TongueOut=1.0（内置参数，无需建参）。"""

    platform = VTubeStudio()
    platform._client = cast(  # noqa: SLF001
        Any,
        _InputParameterClient(_input_parameter_response_with_plugin_parameters()),
    )
    platform.config.model_config_dir = str(tmp_path)

    await platform.reload_model_config("model-1", "avatar")

    request = platform.semantic_adapter.to_tween_requests(  # type: ignore[union-attr]
        [
            SemanticTweenRequest(
                action_parameter_name=SemanticAction.MOUTH_TONGUE_OUT.value,
                end_value=1.0,
                duration=0.1,
                easing="linear",
            )
        ]
    )[0]
    assert request.parameter_name == "TongueOut"
    assert request.end_value == 1.0

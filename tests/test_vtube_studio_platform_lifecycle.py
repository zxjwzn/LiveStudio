"""测试 VTube Studio 平台服务能不能正常开始和结束"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from livestudio.clients.vtube_studio.models import InputParameterListResponse
from livestudio.config import ConfigManager
from livestudio.services.expression.models import NativeExpressionTrigger
from livestudio.services.platforms.vtubestudio import VTubeStudio, VTubeStudioExpressionStateConfig
from livestudio.services.semantic_actions import (
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

    async def get_input_parameters(self) -> InputParameterListResponse:
        if self.response is None:
            raise RuntimeError("api failed")
        return self.response


class _ExpressionClient(_InputParameterClient):
    def __init__(self) -> None:
        super().__init__(_input_parameter_response())
        self.calls: list[tuple[str, bool]] = []

    async def set_expression_active(self, request: Any) -> object:
        self.calls.append((request.data.expression_file, request.data.active))
        return object()


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
                    }
                ],
                "customParameters": [],
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
    model_config.expressions.append(
        VTubeStudioExpressionStateConfig(name="2脸黑", file="2脸黑.exp3.json")
    )
    platform.refresh_expression_adapter(model_config)

    await platform.apply_native_expressions(
        [NativeExpressionTrigger(platform="vtubestudio", native_ref="2脸黑")]
    )

    assert client.calls == [("2脸黑.exp3.json", True)]

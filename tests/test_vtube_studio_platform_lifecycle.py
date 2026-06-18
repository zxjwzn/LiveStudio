"""测试 VTube Studio 平台服务能不能正常开始和结束"""

from __future__ import annotations

from typing import Any, cast

import pytest

from livestudio.clients.vtube_studio.models import InputParameterListResponse
from livestudio.services.platforms.vtubestudio import VTubeStudio
from livestudio.services.semantic_actions import (
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
    platform._initialized = True  # noqa: SLF001
    platform._client = cast(Any, client)  # noqa: SLF001

    async def connect() -> None:
        pass

    async def authenticate() -> None:
        raise RuntimeError("auth failed")

    platform.connect = connect  # type: ignore[method-assign]
    platform.authenticate = authenticate  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="auth failed"):
        await platform.start()

    assert client.disconnect_calls == 1
    assert not platform.is_started
    assert not platform.tween.is_running


async def test_reload_model_config_refreshes_parameter_specs_from_vtube_studio(
    tmp_path,
) -> None:
    platform = VTubeStudio()
    platform._initialized = True  # noqa: SLF001
    platform._client = cast(  # noqa: SLF001
        Any,
        _InputParameterClient(_input_parameter_response()),
    )
    platform.config.model_config_dir = str(tmp_path)

    model_config = await platform.reload_model_config("model-1", "avatar")

    assert model_config.parameter_specs == [spec for spec in model_config.parameter_specs if spec.name == "MouthOpen"]
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


async def test_reload_model_config_keeps_defaults_when_vtube_studio_query_fails(
    tmp_path,
) -> None:
    platform = VTubeStudio()
    platform._initialized = True  # noqa: SLF001
    platform._client = cast(Any, _InputParameterClient())  # noqa: SLF001
    platform.config.model_config_dir = str(tmp_path)

    model_config = await platform.reload_model_config("model-1", "avatar")

    assert any(spec.name == "MouthOpen" for spec in model_config.parameter_specs)

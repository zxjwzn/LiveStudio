from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable
from typing import Any

from livestudio.clients.vtube_studio.examples import (
    build_service,
    example_discover_vtube_studio_port,
    example_request_authentication_token,
)
from livestudio.clients.vtube_studio.models import (
    ColorTintRequest,
    ColorTintRequestData,
    EventSubscriptionRequest,
    EventSubscriptionRequestData,
    HotkeysInCurrentModelRequest,
    HotkeysInCurrentModelRequestData,
    ItemListRequest,
    ItemListRequestData,
    MoveModelRequest,
    MoveModelRequestData,
    ParameterCreationRequest,
    ParameterCreationRequestData,
    PermissionRequest,
    PermissionRequestData,
    TestEvent,
    TestEventConfig,
)
from livestudio.clients.vtube_studio.models.common import ArtMeshMatcher, ColorTint

ExampleCall = Callable[[], Awaitable[Any]]


async def _run_example(name: str, func: ExampleCall) -> None:
    try:
        result = await func()
        print(f"[OK] {name}: {result}")
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")


async def main() -> None:
    """复用单个会话执行示例级集成测试。"""

    authentication_token = os.getenv("VTS_AUTH_TOKEN", "f33861d77db487f8db8012faf583ffc437c3c9410439575aac950fdb6460e5f0")
    permission_name = os.getenv("VTS_TEST_PERMISSION", "LoadCustomImagesAsItems")

    #await _run_example("example_request_authentication_token", example_request_authentication_token)
    await _run_example("example_discover_vtube_studio_port", example_discover_vtube_studio_port)

    if not authentication_token:
        print("[SKIP] authenticated_examples: 未设置环境变量 VTS_AUTH_TOKEN")
        return

    service = await build_service()

    async def connect_and_authenticate() -> bool:
        return await service.connect_and_authenticate(authentication_token)

    await _run_example("example_connect_and_authenticate", connect_and_authenticate)

    if not service.client.is_connected:
        print("[SKIP] authenticated_examples: 连接或认证未成功")
        return

    async def move_model() -> None:
        await service.move_model(
            MoveModelRequest.model_validate(
                {
                    "data": MoveModelRequestData.model_validate(
                        {
                            "time_in_seconds": 0.2,
                            "values_are_relative_to_model": False,
                            "position_x": 0.0,
                            "position_y": 0.35,
                            "rotation": 0.0,
                            "size": -20.0,
                        },
                    ),
                },
            ),
        )

    async def list_hotkeys() -> list[str]:
        response = await service.get_hotkeys(
            HotkeysInCurrentModelRequest.model_validate(
                {"data": HotkeysInCurrentModelRequestData.model_validate({})},
            ),
        )
        return [hotkey.name for hotkey in response.data.available_hotkeys]

    async def create_custom_parameter() -> str:
        response = await service.create_parameter(
            ParameterCreationRequest.model_validate(
                {
                    "data": ParameterCreationRequestData.model_validate(
                        {
                            "parameter_name": "MoodLevel",
                            "explanation": "用于控制开心程度的自定义参数。",
                            "min": 0.0,
                            "max": 1.0,
                            "default_value": 0.0,
                        },
                    ),
                },
            ),
        )
        return response.data.parameter_name

    async def list_scene_items() -> int:
        response = await service.get_items(
            ItemListRequest.model_validate(
                {
                    "data": ItemListRequestData.model_validate(
                        {
                            "include_available_spots": False,
                            "include_item_instances_in_scene": True,
                            "include_available_item_files": False,
                        },
                    ),
                },
            ),
        )
        return response.data.items_in_scene_count

    async def tint_model() -> int:
        response = await service.tint_art_meshes(
            ColorTintRequest.model_validate(
                {
                    "data": ColorTintRequestData.model_validate(
                        {
                            "color_tint": ColorTint.model_validate(
                                {
                                    "colorR": 255,
                                    "colorG": 180,
                                    "colorB": 120,
                                    "colorA": 255,
                                    "mixWithSceneLightingColor": 1.0,
                                },
                            ),
                            "art_mesh_matcher": ArtMeshMatcher.model_validate(
                                {
                                    "tintAll": False,
                                    "nameContains": ["eye"],
                                },
                            ),
                        },
                    ),
                },
            ),
        )
        return response.data.matched_art_meshes

    async def get_permissions() -> list[str]:
        response = await service.get_permissions()
        return [permission.name for permission in response.data.permissions if permission.granted]

    async def request_permission() -> bool | None:
        response = await service.request_permission(
            PermissionRequest(
                data=PermissionRequestData(requestedPermission=permission_name),
            ),
        )
        return response.data.grant_success

    async def subscribe_test_event() -> int:
        listener = service.create_event_listener("TestEvent")
        try:
            await service.subscribe_event(
                EventSubscriptionRequest.model_validate(
                    {
                        "data": EventSubscriptionRequestData.model_validate(
                            {
                                "event_name": "TestEvent",
                                "subscribe": True,
                                "config": TestEventConfig.model_validate(
                                    {"testMessageForEvent": "hello"},
                                ),
                            },
                        ),
                    },
                ),
            )
            event = TestEvent.model_validate((await listener.next_event(timeout=10.0)).model_dump(by_alias=True))
            return event.data.counter
        finally:
            service.remove_event_listener(listener)
            with contextlib.suppress(Exception):
                await service.unsubscribe_event("TestEvent")

    authenticated_examples: list[tuple[str, ExampleCall]] = [
        ("example_move_model", move_model),
        ("example_list_hotkeys", list_hotkeys),
        ("example_create_custom_parameter", create_custom_parameter),
        ("example_list_scene_items", list_scene_items),
        ("example_tint_model", tint_model),
        ("example_get_permissions", get_permissions),
        ("example_request_permission", request_permission),
        ("example_subscribe_test_event", subscribe_test_event),
    ]

    try:
        for name, func in authenticated_examples:
            await _run_example(name, func)
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())

"""Event subscription and event payload models for VTube Studio."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import VTSBaseModel, VTSEmptyData, VTSFlexibleData, VTSRequestEnvelope, VTSResponseEnvelope
from .common import ArtMeshHit, ModelPosition, Vector2, WindowSize

EventName = Literal[
    "TestEvent",
    "ModelLoadedEvent",
    "TrackingStatusChangedEvent",
    "BackgroundChangedEvent",
    "ModelConfigChangedEvent",
    "ModelMovedEvent",
    "ModelOutlineEvent",
    "HotkeyTriggeredEvent",
    "ModelAnimationEvent",
    "ItemEvent",
    "ModelClickedEvent",
    "PostProcessingEvent",
    "Live2DCubismEditorConnectedEvent",
]


class EventSubscriptionConfig(VTSBaseModel):
    """事件订阅配置基类。"""


class TestEventConfig(EventSubscriptionConfig):
    """测试事件配置。"""

    test_message_for_event: str | None = Field(default=None, alias="testMessageForEvent", max_length=32, description="测试事件中回显的文本。")


class ModelLoadedEventConfig(EventSubscriptionConfig):
    """模型加载事件过滤配置。"""

    model_id: list[str] = Field(default_factory=list, alias="modelID", description="可选的模型 ID 过滤列表。")


class ModelOutlineEventConfig(EventSubscriptionConfig):
    """模型轮廓事件配置。"""

    draw: bool = Field(default=False, description="是否在 VTS 窗口中绘制轮廓。")


class HotkeyTriggeredEventConfig(EventSubscriptionConfig):
    """热键触发事件配置。"""

    only_for_action: str | None = Field(default=None, alias="onlyForAction", description="按热键动作过滤。")
    ignore_hotkeys_triggered_by_api: bool = Field(default=False, alias="ignoreHotkeysTriggeredByAPI", description="是否忽略由 API 触发的热键。")


class ModelAnimationEventConfig(EventSubscriptionConfig):
    """模型动画事件配置。"""

    ignore_live2d_items: bool = Field(default=False, alias="ignoreLive2DItems", description="是否忽略 Live2D 道具动画。")
    ignore_idle_animations: bool = Field(default=False, alias="ignoreIdleAnimations", description="是否忽略 Idle 动画。")


class ItemEventConfig(EventSubscriptionConfig):
    """道具事件过滤配置。"""

    item_instance_ids: list[str] = Field(default_factory=list, alias="itemInstanceIDs", description="按实例 ID 过滤。")
    item_file_names: list[str] = Field(default_factory=list, alias="itemFileNames", description="按文件名包含过滤。")


class ModelClickedEventConfig(EventSubscriptionConfig):
    """模型点击事件配置。"""

    only_clicks_on_model: bool = Field(default=True, alias="onlyClicksOnModel", description="是否仅在点击模型时触发。")


class EventSubscriptionRequestData(VTSEmptyData):
    """事件订阅/退订请求负载。"""

    event_name: str | None = Field(default=None, alias="eventName", description="事件名称；取消全部订阅时可为空。")
    subscribe: bool = Field(description="为 true 时订阅，为 false 时退订。")
    config: EventSubscriptionConfig = Field(default_factory=EventSubscriptionConfig, description="事件订阅配置。")


class EventSubscriptionRequest(VTSRequestEnvelope[EventSubscriptionRequestData]):
    """事件订阅请求。"""

    message_type: str = Field(default="EventSubscriptionRequest", alias="messageType", description="订阅或退订事件。")


class EventSubscriptionResponseData(VTSEmptyData):
    """事件订阅响应负载。"""

    subscribed_event_count: int = Field(alias="subscribedEventCount", description="当前会话已订阅事件数量。")
    subscribed_events: list[str] = Field(alias="subscribedEvents", description="当前会话已订阅事件名称列表。")


class EventSubscriptionResponse(VTSResponseEnvelope[EventSubscriptionResponseData]):
    """事件订阅响应信封。"""


class TestEventData(VTSEmptyData):
    your_test_message: str = Field(alias="yourTestMessage", description="订阅时配置的测试文本。")
    counter: int = Field(description="VTS 启动后的秒级计数器。")


class ModelLoadedEventData(VTSEmptyData):
    model_loaded: bool = Field(alias="modelLoaded", description="模型是否被加载；false 表示卸载。")
    model_name: str = Field(alias="modelName", description="模型名称。")
    model_id: str = Field(alias="modelID", description="模型唯一 ID。")


class TrackingStatusChangedEventData(VTSEmptyData):
    face_found: bool = Field(alias="faceFound", description="是否检测到人脸。")
    left_hand_found: bool = Field(alias="leftHandFound", description="是否检测到左手。")
    right_hand_found: bool = Field(alias="rightHandFound", description="是否检测到右手。")


class BackgroundChangedEventData(VTSEmptyData):
    background_name: str = Field(alias="backgroundName", description="背景名称。")


class ModelConfigChangedEventData(VTSEmptyData):
    model_id: str = Field(alias="modelID", description="模型 ID。")
    model_name: str = Field(alias="modelName", description="模型名称。")
    hotkey_config_changed: bool = Field(alias="hotkeyConfigChanged", description="是否为热键配置变更。")


class ModelMovedEventData(VTSEmptyData):
    model_id: str = Field(alias="modelID", description="模型 ID。")
    model_name: str = Field(alias="modelName", description="模型名称。")
    model_position: ModelPosition = Field(alias="modelPosition", description="模型当前位置、旋转与缩放。")


class ModelOutlineEventData(VTSEmptyData):
    model_name: str = Field(alias="modelName", description="模型名称。")
    model_id: str = Field(alias="modelID", description="模型 ID。")
    convex_hull: list[Vector2] = Field(alias="convexHull", min_length=3, description="模型近似凸包点集。")
    convex_hull_center: Vector2 = Field(alias="convexHullCenter", description="凸包中心点。")
    window_size: WindowSize = Field(alias="windowSize", description="当前 VTS 窗口尺寸。")


class HotkeyTriggeredEventData(VTSEmptyData):
    hotkey_id: str = Field(alias="hotkeyID", description="热键 ID。")
    hotkey_name: str = Field(alias="hotkeyName", description="热键名称。")
    hotkey_action: str = Field(alias="hotkeyAction", description="热键动作类型。")
    hotkey_file: str = Field(alias="hotkeyFile", description="热键关联文件。")
    hotkey_triggered_by_api: bool = Field(alias="hotkeyTriggeredByAPI", description="是否由 API 触发。")
    model_id: str = Field(alias="modelID", description="关联模型 ID。")
    model_name: str = Field(alias="modelName", description="关联模型名称。")
    is_live2d_item: bool = Field(alias="isLive2DItem", description="是否为 Live2D 道具热键。")


class ModelAnimationEventData(VTSEmptyData):
    animation_event_type: str = Field(alias="animationEventType", description="事件类型。")
    animation_event_time: float = Field(alias="animationEventTime", description="事件在动画中的时间点。")
    animation_event_data: str = Field(alias="animationEventData", description="自定义事件文本或保留关键字。")
    animation_name: str = Field(alias="animationName", description="动画文件名。")
    animation_length: float = Field(alias="animationLength", description="动画总长度，秒。")
    is_idle_animation: bool = Field(alias="isIdleAnimation", description="是否为 Idle 动画。")
    model_id: str = Field(alias="modelID", description="模型 ID。")
    model_name: str = Field(alias="modelName", description="模型名称。")
    is_live2d_item: bool = Field(alias="isLive2DItem", description="是否为 Live2D 道具动画。")


class ItemEventData(VTSEmptyData):
    item_event_type: str = Field(alias="itemEventType", description="道具事件类型。")
    item_instance_id: str = Field(alias="itemInstanceID", description="道具实例 ID。")
    item_file_name: str = Field(alias="itemFileName", description="道具文件名。")
    item_position: Vector2 = Field(alias="itemPosition", description="道具事件位置。")


class ModelClickedEventData(VTSEmptyData):
    model_loaded: bool = Field(alias="modelLoaded", description="当前是否已加载模型。")
    loaded_model_id: str | None = Field(default=None, alias="loadedModelID", description="当前加载模型 ID。")
    loaded_model_name: str | None = Field(default=None, alias="loadedModelName", description="当前加载模型名称。")
    model_was_clicked: bool = Field(alias="modelWasClicked", description="本次点击是否命中模型。")
    mouse_button_id: int = Field(alias="mouseButtonID", description="鼠标按钮 ID。")
    click_position: Vector2 = Field(alias="clickPosition", description="点击位置。")
    window_size: WindowSize = Field(alias="windowSize", description="当前窗口大小。")
    clicked_art_mesh_count: int = Field(alias="clickedArtMeshCount", description="命中的 ArtMesh 数量。")
    art_mesh_hits: list[ArtMeshHit] = Field(alias="artMeshHits", description="所有命中的 ArtMesh 详情。")


class PostProcessingEventData(VTSEmptyData):
    current_on_state: bool = Field(alias="currentOnState", description="后处理系统是否开启。")
    current_preset: str = Field(alias="currentPreset", description="当前预设名称。")


class Live2DCubismEditorConnectedEventData(VTSEmptyData):
    trying_to_connect: bool = Field(alias="tryingToConnect", description="VTS 是否正在尝试连接 Cubism Editor。")
    connected: bool = Field(description="是否已完成连接与鉴权。")
    should_send_parameters: bool = Field(alias="shouldSendParameters", description="是否开启参数直传。")


class VTSEventEnvelope(VTSResponseEnvelope[VTSFlexibleData]):
    """通用事件信封。"""


class TestEvent(VTSResponseEnvelope[TestEventData]):
    """测试事件信封。"""


class ModelLoadedEvent(VTSResponseEnvelope[ModelLoadedEventData]):
    """模型加载事件信封。"""


class TrackingStatusChangedEvent(VTSResponseEnvelope[TrackingStatusChangedEventData]):
    """追踪状态变更事件信封。"""


class BackgroundChangedEvent(VTSResponseEnvelope[BackgroundChangedEventData]):
    """背景变更事件信封。"""


class ModelConfigChangedEvent(VTSResponseEnvelope[ModelConfigChangedEventData]):
    """模型配置变更事件信封。"""


class ModelMovedEvent(VTSResponseEnvelope[ModelMovedEventData]):
    """模型移动事件信封。"""


class ModelOutlineEvent(VTSResponseEnvelope[ModelOutlineEventData]):
    """模型轮廓事件信封。"""


class HotkeyTriggeredEvent(VTSResponseEnvelope[HotkeyTriggeredEventData]):
    """热键触发事件信封。"""


class ModelAnimationEvent(VTSResponseEnvelope[ModelAnimationEventData]):
    """模型动画事件信封。"""


class ItemEvent(VTSResponseEnvelope[ItemEventData]):
    """道具事件信封。"""


class ModelClickedEvent(VTSResponseEnvelope[ModelClickedEventData]):
    """模型点击事件信封。"""


class PostProcessingEvent(VTSResponseEnvelope[PostProcessingEventData]):
    """后处理事件信封。"""


class Live2DCubismEditorConnectedEvent(VTSResponseEnvelope[Live2DCubismEditorConnectedEventData]):
    """Cubism Editor 连接状态事件信封。"""
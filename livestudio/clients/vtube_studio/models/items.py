"""与道具和后处理相关的请求/响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import VTSEmptyData, VTSRequestEnvelope, VTSResponseEnvelope
from .common import (
    ItemFile,
    ItemInstance,
    ItemMove,
    MovedItemResult,
    PinInfo,
    PostProcessingEffect,
    PostProcessingValue,
    UnloadedItem,
)


class NDIConfigRequestData(VTSEmptyData):
    """查询或设置 NDI 配置。"""

    set_new_config: bool = Field(
        alias="setNewConfig",
        description="是否写入新配置；为 `false` 时仅查询当前配置。",
    )
    ndi_active: bool | None = Field(
        default=None,
        alias="ndiActive",
        description="是否启用 NDI。",
    )
    use_ndi5: bool | None = Field(
        default=None,
        alias="useNDI5",
        description="是否使用 NDI 5。",
    )
    use_custom_resolution: bool | None = Field(
        default=None,
        alias="useCustomResolution",
        description="是否启用自定义分辨率。",
    )
    custom_width_ndi: int | None = Field(
        default=None,
        alias="customWidthNDI",
        description="自定义宽度。",
    )
    custom_height_ndi: int | None = Field(
        default=None,
        alias="customHeightNDI",
        description="自定义高度。",
    )


class NDIConfigRequest(VTSRequestEnvelope[NDIConfigRequestData]):
    """NDI 配置请求。"""

    message_type: str = Field(
        default="NDIConfigRequest",
        alias="messageType",
        description="请求查询或更新 NDI 配置。",
    )


class NDIConfigResponseData(VTSEmptyData):
    """NDI 配置响应。"""

    set_new_config: bool = Field(
        alias="setNewConfig",
        description="响应中回显的配置模式标记。",
    )
    ndi_active: bool = Field(alias="ndiActive", description="NDI 是否启用。")
    use_ndi5: bool = Field(alias="useNDI5", description="是否使用 NDI 5。")
    use_custom_resolution: bool = Field(
        alias="useCustomResolution",
        description="是否启用自定义分辨率。",
    )
    custom_width_ndi: int = Field(alias="customWidthNDI", description="当前 NDI 宽度。")
    custom_height_ndi: int = Field(
        alias="customHeightNDI",
        description="当前 NDI 高度。",
    )


class NDIConfigResponse(VTSResponseEnvelope[NDIConfigResponseData]):
    """NDI 配置响应信封。"""


class ItemAnimationControlRequestData(VTSEmptyData):
    """控制道具动画、亮度与透明度。"""

    item_instance_id: str = Field(
        alias="itemInstanceID",
        description="目标道具实例 ID。",
    )
    framerate: float = Field(default=-1, description="目标帧率，-1 表示不修改。")
    frame: int = Field(default=-1, description="目标帧索引，-1 表示不修改。")
    brightness: float = Field(default=-1, description="亮度，-1 表示不修改。")
    opacity: float = Field(default=-1, description="透明度，-1 表示不修改。")
    set_auto_stop_frames: bool = Field(
        alias="setAutoStopFrames",
        description="是否更新自动停止帧列表。",
    )
    auto_stop_frames: list[int] = Field(
        default_factory=list,
        alias="autoStopFrames",
        description="自动停止帧索引列表。",
    )
    set_animation_play_state: bool = Field(
        alias="setAnimationPlayState",
        description="是否更新动画播放状态。",
    )
    animation_play_state: bool = Field(
        alias="animationPlayState",
        description="目标动画播放状态。",
    )


class ItemAnimationControlRequest(VTSRequestEnvelope[ItemAnimationControlRequestData]):
    """道具动画控制请求。"""

    message_type: str = Field(
        default="ItemAnimationControlRequest",
        alias="messageType",
        description="请求控制道具动画播放与显示属性。",
    )


class ItemAnimationControlResponseData(VTSEmptyData):
    """道具动画控制响应。"""

    frame: int = Field(description="当前帧索引。")
    animation_playing: bool = Field(
        alias="animationPlaying",
        description="动画当前是否播放中。",
    )


class ItemAnimationControlResponse(
    VTSResponseEnvelope[ItemAnimationControlResponseData],
):
    """道具动画控制响应信封。"""


class ItemSortRequestData(VTSEmptyData):
    """设置道具模型内排序。"""

    item_instance_id: str = Field(
        alias="itemInstanceID",
        description="目标道具实例 ID。",
    )
    front_on: bool = Field(alias="frontOn", description="是否启用前半部分插入。")
    back_on: bool = Field(alias="backOn", description="是否启用后半部分插入。")
    set_split_point: str = Field(alias="setSplitPoint", description="分割点解释方式。")
    set_front_order: str = Field(
        alias="setFrontOrder",
        description="前半部分层级解释方式。",
    )
    set_back_order: str = Field(
        alias="setBackOrder",
        description="后半部分层级解释方式。",
    )
    split_at: str = Field(alias="splitAt", description="Live2D 道具分割点。")
    within_model_order_front: str = Field(
        alias="withinModelOrderFront",
        description="前半部分插入层位。",
    )
    within_model_order_back: str = Field(
        alias="withinModelOrderBack",
        description="后半部分插入层位。",
    )


class ItemSortRequest(VTSRequestEnvelope[ItemSortRequestData]):
    """道具模型内排序请求。"""

    message_type: str = Field(
        default="ItemSortRequest",
        alias="messageType",
        description="请求设置道具在模型内部的前后层位。",
    )


class ItemSortResponseData(VTSEmptyData):
    """道具模型内排序响应。"""

    item_instance_id: str = Field(
        alias="itemInstanceID",
        description="目标道具实例 ID。",
    )
    model_loaded: bool = Field(alias="modelLoaded", description="当前是否加载主模型。")
    model_id: str = Field(alias="modelID", description="当前主模型 ID。")
    model_name: str = Field(alias="modelName", description="当前主模型名称。")
    loaded_model_had_requested_front_layer: bool = Field(
        alias="loadedModelHadRequestedFrontLayer",
        description="当前模型是否存在请求的前层插入点。",
    )
    loaded_model_had_requested_back_layer: bool = Field(
        alias="loadedModelHadRequestedBackLayer",
        description="当前模型是否存在请求的后层插入点。",
    )


class ItemSortResponse(VTSResponseEnvelope[ItemSortResponseData]):
    """道具模型内排序响应信封。"""


class ArtMeshSelectionRequestData(VTSEmptyData):
    """请求用户选择 ArtMesh。"""

    text_override: str | None = Field(
        default=None,
        alias="textOverride",
        description="覆盖顶部提示文本。",
    )
    help_override: str | None = Field(
        default=None,
        alias="helpOverride",
        description="覆盖帮助弹窗文本。",
    )
    requested_art_mesh_count: int = Field(
        alias="requestedArtMeshCount",
        description="要求用户选择的 ArtMesh 数量；<=0 表示任意数量。",
    )
    active_art_meshes: list[str] = Field(
        default_factory=list,
        alias="activeArtMeshes",
        description="初始高亮的 ArtMesh ID 列表。",
    )


class ArtMeshSelectionRequest(VTSRequestEnvelope[ArtMeshSelectionRequestData]):
    """ArtMesh 选择请求。"""

    message_type: str = Field(
        default="ArtMeshSelectionRequest",
        alias="messageType",
        description="请求 VTube Studio 弹出 ArtMesh 选择界面。",
    )


class ArtMeshSelectionResponseData(VTSEmptyData):
    """ArtMesh 选择响应。"""

    success: bool = Field(description="用户是否确认选择。")
    active_art_meshes: list[str] = Field(
        alias="activeArtMeshes",
        description="用户最终激活的 ArtMesh 列表。",
    )
    inactive_art_meshes: list[str] = Field(
        alias="inactiveArtMeshes",
        description="用户最终未激活的 ArtMesh 列表。",
    )


class ArtMeshSelectionResponse(VTSResponseEnvelope[ArtMeshSelectionResponseData]):
    """ArtMesh 选择响应信封。"""


class ItemListRequestData(VTSEmptyData):
    """查询道具列表。"""

    include_available_spots: bool = Field(
        alias="includeAvailableSpots",
        description="是否返回当前可用排序层位。",
    )
    include_item_instances_in_scene: bool = Field(
        alias="includeItemInstancesInScene",
        description="是否返回场景中已加载实例。",
    )
    include_available_item_files: bool = Field(
        alias="includeAvailableItemFiles",
        description="是否扫描磁盘返回可加载道具文件。",
    )
    only_items_with_file_name: str | None = Field(
        default=None,
        alias="onlyItemsWithFileName",
        description="可选：按文件名过滤。",
    )
    only_items_with_instance_id: str | None = Field(
        default=None,
        alias="onlyItemsWithInstanceID",
        description="可选：按实例 ID 过滤。",
    )


class ItemListRequest(VTSRequestEnvelope[ItemListRequestData]):
    """道具列表查询请求。"""

    message_type: str = Field(
        default="ItemListRequest",
        alias="messageType",
        description="请求场景道具和可加载道具信息。",
    )


class ItemListResponseData(VTSEmptyData):
    """道具列表响应。"""

    items_in_scene_count: int = Field(
        alias="itemsInSceneCount",
        description="场景中道具实例数量。",
    )
    total_items_allowed_count: int = Field(
        alias="totalItemsAllowedCount",
        description="当前场景允许的最大道具数量。",
    )
    can_load_items_right_now: bool = Field(
        alias="canLoadItemsRightNow",
        description="当前是否允许加载道具。",
    )
    available_spots: list[int] = Field(
        alias="availableSpots",
        description="可用排序层位。",
    )
    item_instances_in_scene: list[ItemInstance] = Field(
        alias="itemInstancesInScene",
        description="场景中的道具实例。",
    )
    available_item_files: list[ItemFile] = Field(
        alias="availableItemFiles",
        description="本地可加载道具文件。",
    )


class ItemListResponse(VTSResponseEnvelope[ItemListResponseData]):
    """道具列表响应信封。"""


class ItemLoadRequestData(VTSEmptyData):
    """加载道具。"""

    file_name: str = Field(
        alias="fileName",
        description="待加载道具文件名。若加载自定义数据，仍需提供合法文件名。",
    )
    position_x: float = Field(
        alias="positionX",
        ge=-1000,
        le=1000,
        description="初始 X 坐标。",
    )
    position_y: float = Field(
        alias="positionY",
        ge=-1000,
        le=1000,
        description="初始 Y 坐标。",
    )
    size: float = Field(ge=0, le=1, description="初始尺寸。")
    rotation: float = Field(ge=-360, le=360, description="初始旋转角度。")
    fade_time: float = Field(alias="fadeTime", ge=0, le=2, description="淡入时长，秒。")
    order: int = Field(description="期望加载层位。")
    fail_if_order_taken: bool = Field(
        alias="failIfOrderTaken",
        description="若层位被占用是否直接报错。",
    )
    smoothing: float = Field(ge=0, le=1, description="位置平滑。")
    censored: bool = Field(description="是否打码。")
    flipped: bool = Field(description="是否翻转。")
    locked: bool = Field(description="是否锁定。")
    unload_when_plugin_disconnects: bool = Field(
        alias="unloadWhenPluginDisconnects",
        description="插件断开连接时是否自动卸载。",
    )
    custom_data_base64: str | None = Field(
        default=None,
        alias="customDataBase64",
        description="可选 Base64 PNG/JPG/GIF 数据。",
    )
    custom_data_ask_user_first: bool | None = Field(
        default=None,
        alias="customDataAskUserFirst",
        description="加载自定义图片前是否询问用户。",
    )
    custom_data_skip_asking_user_if_whitelisted: bool | None = Field(
        default=None,
        alias="customDataSkipAskingUserIfWhitelisted",
        description="若已加入白名单是否跳过询问。",
    )
    custom_data_ask_timer: float | None = Field(
        default=None,
        alias="customDataAskTimer",
        description="自定义图片授权弹窗倒计时秒数。",
    )


class ItemLoadRequest(VTSRequestEnvelope[ItemLoadRequestData]):
    """加载道具请求。"""

    message_type: str = Field(
        default="ItemLoadRequest",
        alias="messageType",
        description="请求将道具加载进当前场景。",
    )


class ItemLoadResponseData(VTSEmptyData):
    """加载道具响应。"""

    instance_id: str = Field(alias="instanceID", description="新加载道具实例 ID。")
    file_name: str = Field(alias="fileName", description="实际加载的文件名。")


class ItemLoadResponse(VTSResponseEnvelope[ItemLoadResponseData]):
    """加载道具响应信封。"""


class ItemUnloadRequestData(VTSEmptyData):
    """卸载道具。"""

    unload_all_in_scene: bool = Field(
        alias="unloadAllInScene",
        description="是否卸载场景中全部道具。",
    )
    unload_all_loaded_by_this_plugin: bool = Field(
        alias="unloadAllLoadedByThisPlugin",
        description="是否卸载本插件加载的全部道具。",
    )
    allow_unloading_items_loaded_by_user_or_other_plugins: bool = Field(
        alias="allowUnloadingItemsLoadedByUserOrOtherPlugins",
        description="是否允许卸载用户或其他插件加载的道具。",
    )
    instance_ids: list[str] = Field(
        default_factory=list,
        alias="instanceIDs",
        description="待卸载实例 ID 列表。",
    )
    file_names: list[str] = Field(
        default_factory=list,
        alias="fileNames",
        description="待卸载文件名列表。",
    )


class ItemUnloadRequest(VTSRequestEnvelope[ItemUnloadRequestData]):
    """卸载道具请求。"""

    message_type: str = Field(
        default="ItemUnloadRequest",
        alias="messageType",
        description="请求从场景中移除道具。",
    )


class ItemUnloadResponseData(VTSEmptyData):
    """卸载道具响应。"""

    unloaded_items: list[UnloadedItem] = Field(
        alias="unloadedItems",
        description="实际被卸载的道具列表。",
    )


class ItemUnloadResponse(VTSResponseEnvelope[ItemUnloadResponseData]):
    """卸载道具响应信封。"""


class ItemMoveRequestData(VTSEmptyData):
    """批量移动道具。"""

    items_to_move: list[ItemMove] = Field(
        alias="itemsToMove",
        min_length=1,
        max_length=64,
        description="待移动的道具列表。",
    )


class ItemMoveRequest(VTSRequestEnvelope[ItemMoveRequestData]):
    """批量移动道具请求。"""

    message_type: str = Field(
        default="ItemMoveRequest",
        alias="messageType",
        description="请求批量移动一个或多个道具。",
    )


class ItemMoveResponseData(VTSEmptyData):
    """批量移动道具响应。"""

    moved_items: list[MovedItemResult] = Field(
        alias="movedItems",
        description="每个道具的移动结果。",
    )


class ItemMoveResponse(VTSResponseEnvelope[ItemMoveResponseData]):
    """批量移动道具响应信封。"""


class ItemPinRequestData(VTSEmptyData):
    """将道具固定到模型。"""

    pin: bool = Field(description="是否执行固定；为 `false` 时表示取消固定。")
    item_instance_id: str = Field(
        alias="itemInstanceID",
        description="目标道具实例 ID。",
    )
    angle_relative_to: (
        Literal[
            "RelativeToWorld",
            "RelativeToCurrentItemRotation",
            "RelativeToModel",
            "RelativeToPinPosition",
        ]
        | None
    ) = Field(default=None, alias="angleRelativeTo", description="角度参考系。")
    size_relative_to: Literal["RelativeToWorld", "RelativeToCurrentItemSize"] | None = (
        Field(default=None, alias="sizeRelativeTo", description="尺寸参考系。")
    )
    vertex_pin_type: Literal["Provided", "Center", "Random"] | None = Field(
        default=None,
        alias="vertexPinType",
        description="固定点类型。",
    )
    pin_info: PinInfo | None = Field(
        default=None,
        alias="pinInfo",
        description="固定到模型时的详细定位信息。",
    )


class ItemPinRequest(VTSRequestEnvelope[ItemPinRequestData]):
    """固定道具请求。"""

    message_type: str = Field(
        default="ItemPinRequest",
        alias="messageType",
        description="请求将道具固定到模型或取消固定。",
    )


class ItemPinResponseData(VTSEmptyData):
    """固定道具响应。"""

    is_pinned: bool = Field(alias="isPinned", description="该道具当前是否已固定。")
    item_instance_id: str = Field(alias="itemInstanceID", description="道具实例 ID。")
    item_file_name: str = Field(alias="itemFileName", description="道具文件名。")


class ItemPinResponse(VTSResponseEnvelope[ItemPinResponseData]):
    """固定道具响应信封。"""


class PostProcessingListRequestData(VTSEmptyData):
    """查询后处理系统状态。"""

    fill_post_processing_presets_array: bool = Field(
        alias="fillPostProcessingPresetsArray",
        description="是否返回预设名称列表。",
    )
    fill_post_processing_effects_array: bool = Field(
        alias="fillPostProcessingEffectsArray",
        description="是否返回效果与配置明细。",
    )
    effect_id_filter: list[str] = Field(
        default_factory=list,
        alias="effectIDFilter",
        description="可选效果过滤列表。",
    )


class PostProcessingListRequest(VTSRequestEnvelope[PostProcessingListRequestData]):
    """后处理列表请求。"""

    message_type: str = Field(
        default="PostProcessingListRequest",
        alias="messageType",
        description="请求后处理系统状态、效果列表与预设。",
    )


class PostProcessingListResponseData(VTSEmptyData):
    """后处理列表响应。"""

    post_processing_supported: bool = Field(
        alias="postProcessingSupported",
        description="当前平台是否支持后处理。",
    )
    post_processing_active: bool = Field(
        alias="postProcessingActive",
        description="后处理是否全局启用。",
    )
    can_send_post_processing_update_request_right_now: bool = Field(
        alias="canSendPostProcessingUpdateRequestRightNow",
        description="当前是否允许更新后处理配置。",
    )
    restricted_effects_allowed: bool = Field(
        alias="restrictedEffectsAllowed",
        description="用户是否允许受限/实验性效果。",
    )
    preset_is_active: bool = Field(
        alias="presetIsActive",
        description="当前是否有激活中的预设。",
    )
    active_preset: str = Field(alias="activePreset", description="当前激活预设名称。")
    preset_count: int = Field(alias="presetCount", description="返回的预设数量。")
    active_effect_count: int = Field(
        alias="activeEffectCount",
        description="当前激活中的效果数量。",
    )
    effect_count_before_filter: int = Field(
        alias="effectCountBeforeFilter",
        description="过滤前效果数量。",
    )
    config_count_before_filter: int = Field(
        alias="configCountBeforeFilter",
        description="过滤前配置项数量。",
    )
    effect_count_after_filter: int = Field(
        alias="effectCountAfterFilter",
        description="过滤后效果数量。",
    )
    config_count_after_filter: int = Field(
        alias="configCountAfterFilter",
        description="过滤后配置项数量。",
    )
    post_processing_effects: list[PostProcessingEffect] = Field(
        alias="postProcessingEffects",
        description="后处理效果列表。",
    )
    post_processing_presets: list[str] = Field(
        alias="postProcessingPresets",
        description="后处理预设名称列表。",
    )


class PostProcessingListResponse(VTSResponseEnvelope[PostProcessingListResponseData]):
    """后处理列表响应信封。"""


class PostProcessingUpdateRequestData(VTSEmptyData):
    """更新后处理配置。"""

    post_processing_on: bool = Field(
        alias="postProcessingOn",
        description="是否全局启用后处理。",
    )
    set_post_processing_preset: bool = Field(
        alias="setPostProcessingPreset",
        description="是否加载预设。",
    )
    set_post_processing_values: bool = Field(
        alias="setPostProcessingValues",
        description="是否直接设置配置值。",
    )
    preset_to_set: str = Field(
        alias="presetToSet",
        description="待加载预设名称，不含扩展名。",
    )
    post_processing_fade_time: float = Field(
        alias="postProcessingFadeTime",
        ge=0,
        le=2,
        description="效果过渡时长，秒。",
    )
    set_all_other_values_to_default: bool = Field(
        alias="setAllOtherValuesToDefault",
        description="未指定配置项是否恢复默认值。",
    )
    using_restricted_effects: bool = Field(
        alias="usingRestrictedEffects",
        description="是否显式声明使用受限效果。",
    )
    randomize_all: bool = Field(
        alias="randomizeAll",
        description="是否随机化全部效果配置。",
    )
    randomize_all_chaos_level: float = Field(
        alias="randomizeAllChaosLevel",
        ge=0,
        le=1,
        description="随机化混乱程度。",
    )
    post_processing_values: list[PostProcessingValue] = Field(
        default_factory=list,
        alias="postProcessingValues",
        description="待设置的配置项列表。",
    )


class PostProcessingUpdateRequest(VTSRequestEnvelope[PostProcessingUpdateRequestData]):
    """更新后处理配置请求。"""

    message_type: str = Field(
        default="PostProcessingUpdateRequest",
        alias="messageType",
        description="请求更新后处理开关、预设或配置值。",
    )


class PostProcessingUpdateResponseData(VTSEmptyData):
    """更新后处理配置响应。"""

    post_processing_active: bool = Field(
        alias="postProcessingActive",
        description="更新后后处理是否激活。",
    )
    preset_is_active: bool = Field(
        alias="presetIsActive",
        description="更新后是否有激活中的预设。",
    )
    active_preset: str = Field(
        alias="activePreset",
        description="更新后当前激活的预设名称。",
    )
    active_effect_count: int = Field(
        alias="activeEffectCount",
        description="更新后处于激活状态的效果数量。",
    )


class PostProcessingUpdateResponse(
    VTSResponseEnvelope[PostProcessingUpdateResponseData],
):
    """更新后处理配置响应信封。"""

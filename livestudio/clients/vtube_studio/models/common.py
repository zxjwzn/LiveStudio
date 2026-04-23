"""多个 VTube Studio API 请求共用的领域模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import VTSBaseModel


class ModelPosition(VTSBaseModel):
    """模型位置、旋转与缩放。"""

    position_x: float = Field(
        alias="positionX",
        description="模型 X 坐标，通常范围为 -1000 到 1000。",
    )
    position_y: float = Field(
        alias="positionY",
        description="模型 Y 坐标，通常范围为 -1000 到 1000。",
    )
    rotation: float = Field(description="模型旋转角度，单位为度。")
    size: float = Field(description="模型大小，文档通常使用 -100 到 100。")


class Vector2(VTSBaseModel):
    """二维坐标。"""

    x: float = Field(description="X 坐标。")
    y: float = Field(description="Y 坐标。")


class WindowSize(VTSBaseModel):
    """窗口像素尺寸。"""

    x: int = Field(description="窗口宽度，像素。")
    y: int = Field(description="窗口高度，像素。")


class AvailableModel(VTSBaseModel):
    """可用模型摘要。"""

    model_loaded: bool = Field(
        alias="modelLoaded",
        description="该模型当前是否已加载。",
    )
    model_name: str = Field(alias="modelName", description="模型显示名称。")
    model_id: str = Field(alias="modelID", description="模型唯一标识。")
    vts_model_name: str = Field(
        alias="vtsModelName",
        description="VTS 模型配置文件名。",
    )
    vts_model_icon_name: str = Field(
        alias="vtsModelIconName",
        description="模型图标文件名。",
    )


class Hotkey(VTSBaseModel):
    """热键定义。"""

    name: str = Field(description="热键名称。")
    type: str = Field(description="热键动作类型，如 `ToggleExpression`。")
    description: str = Field(description="热键用途说明。")
    file: str = Field(description="关联文件名；若无则为空字符串。")
    hotkey_id: str = Field(alias="hotkeyID", description="热键唯一标识。")
    key_combination: list[str] = Field(
        alias="keyCombination",
        description="按键组合列表；当前通常为空。",
    )
    on_screen_button_id: int = Field(
        alias="onScreenButtonID",
        description="屏幕按钮 ID，-1 表示未设置。",
    )


class ExpressionHotkeyRef(VTSBaseModel):
    """表达式关联热键。"""

    name: str = Field(description="热键名称。")
    id: str = Field(description="热键唯一标识。")


class ExpressionParameter(VTSBaseModel):
    """表达式参数。"""

    name: str = Field(description="Live2D 参数 ID。")
    value: float = Field(description="表达式目标值。")


class ExpressionState(VTSBaseModel):
    """表达式状态。"""

    name: str = Field(description="表达式名称，不带扩展名。")
    file: str = Field(description="表达式文件名。")
    active: bool = Field(description="表达式当前是否激活。")
    deactivate_when_key_is_let_go: bool = Field(
        alias="deactivateWhenKeyIsLetGo",
        description="按键松开时是否自动取消。",
    )
    auto_deactivate_after_seconds: bool = Field(
        alias="autoDeactivateAfterSeconds",
        description="是否启用定时自动取消。",
    )
    seconds_remaining: float = Field(
        alias="secondsRemaining",
        description="剩余自动取消秒数。",
    )
    used_in_hotkeys: list[ExpressionHotkeyRef] = Field(
        alias="usedInHotkeys",
        description="引用该表达式的热键列表。",
    )
    parameters: list[ExpressionParameter] = Field(
        description="表达式中涉及的参数与目标值。",
    )


class ParameterInfo(VTSBaseModel):
    """输入参数或 Live2D 参数信息。"""

    name: str = Field(description="参数名称或 ID。")
    added_by: str | None = Field(
        default=None,
        alias="addedBy",
        description="参数创建者。默认参数通常为 `VTube Studio`。",
    )
    value: float = Field(description="当前值。")
    min: float = Field(description="建议最小值。")
    max: float = Field(description="建议最大值。")
    default_value: float = Field(alias="defaultValue", description="默认值。")


class PhysicsGroup(VTSBaseModel):
    """物理分组信息。"""

    group_id: str = Field(alias="groupID", description="物理分组唯一 ID。")
    group_name: str = Field(alias="groupName", description="物理分组显示名称。")
    strength_multiplier: float = Field(
        alias="strengthMultiplier",
        description="物理强度倍率。",
    )
    wind_multiplier: float = Field(alias="windMultiplier", description="风力倍率。")


class PhysicsOverride(VTSBaseModel):
    """物理覆盖设置。"""

    id: str = Field(description="物理分组 ID；设置基础值时可为空。")
    value: float = Field(description="目标覆盖值。")
    set_base_value: bool = Field(
        alias="setBaseValue",
        description="是否覆盖基础值而非特定分组。",
    )
    override_seconds: float = Field(
        alias="overrideSeconds",
        ge=0.5,
        le=5.0,
        description="覆盖持续秒数。",
    )


class ColorTint(VTSBaseModel):
    """ArtMesh 颜色覆盖。"""

    color_r: int = Field(alias="colorR", ge=0, le=255, description="红色通道。")
    color_g: int = Field(alias="colorG", ge=0, le=255, description="绿色通道。")
    color_b: int = Field(alias="colorB", ge=0, le=255, description="蓝色通道。")
    color_a: int = Field(alias="colorA", ge=0, le=255, description="透明度通道。")
    mix_with_scene_lighting_color: float | None = Field(
        default=None,
        alias="mixWithSceneLightingColor",
        ge=0,
        le=1,
        description="与场景光照颜色混合比。",
    )


class ArtMeshMatcher(VTSBaseModel):
    """ArtMesh 匹配条件。"""

    tint_all: bool = Field(
        default=False,
        alias="tintAll",
        description="是否对全模型应用着色。",
    )
    art_mesh_number: list[int] = Field(
        default_factory=list,
        alias="artMeshNumber",
        description="按序号匹配 ArtMesh。",
    )
    name_exact: list[str] = Field(
        default_factory=list,
        alias="nameExact",
        description="按名称精确匹配。",
    )
    name_contains: list[str] = Field(
        default_factory=list,
        alias="nameContains",
        description="按名称包含匹配。",
    )
    tag_exact: list[str] = Field(
        default_factory=list,
        alias="tagExact",
        description="按标签精确匹配。",
    )
    tag_contains: list[str] = Field(
        default_factory=list,
        alias="tagContains",
        description="按标签包含匹配。",
    )


class CapturePart(VTSBaseModel):
    """场景采样区域颜色。"""

    active: bool = Field(description="该采样区域是否启用。")
    color_r: int = Field(alias="colorR", description="红色均值。")
    color_g: int = Field(alias="colorG", description="绿色均值。")
    color_b: int = Field(alias="colorB", description="蓝色均值。")


class InjectParameterValue(VTSBaseModel):
    """待注入参数值。"""

    id: str = Field(description="参数 ID。")
    value: float = Field(ge=-1000000, le=1000000, description="目标值。")
    weight: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="混合权重；`set` 模式可选。",
    )


class ItemFile(VTSBaseModel):
    """可加载道具文件。"""

    file_name: str = Field(alias="fileName", description="道具文件名或文件夹名。")
    type: str = Field(description="道具类型，如 `PNG`、`Live2D`。")
    loaded_count: int = Field(alias="loadedCount", description="当前已加载实例数量。")


class ItemInstance(VTSBaseModel):
    """场景中的道具实例。"""

    file_name: str = Field(alias="fileName", description="道具文件名。")
    instance_id: str = Field(alias="instanceID", description="实例唯一标识。")
    order: int = Field(description="场景排序层。")
    type: str = Field(description="道具类型。")
    censored: bool = Field(description="是否打码。")
    flipped: bool = Field(description="是否翻转。")
    locked: bool = Field(description="是否锁定。")
    smoothing: float = Field(description="平滑值。")
    framerate: float = Field(description="动画帧率。")
    frame_count: int = Field(
        alias="frameCount",
        description="总帧数，非动画通常为 -1。",
    )
    current_frame: int = Field(alias="currentFrame", description="当前帧。")
    pinned_to_model: bool = Field(alias="pinnedToModel", description="是否固定到模型。")
    pinned_model_id: str = Field(alias="pinnedModelID", description="固定到的模型 ID。")
    pinned_art_mesh_id: str = Field(
        alias="pinnedArtMeshID",
        description="固定到的 ArtMesh ID。",
    )
    group_name: str = Field(alias="groupName", description="道具分组名称。")
    scene_name: str = Field(alias="sceneName", description="场景名称。")
    from_workshop: bool = Field(alias="fromWorkshop", description="是否来自创意工坊。")


class UnloadedItem(VTSBaseModel):
    """卸载的道具摘要。"""

    instance_id: str = Field(alias="instanceID", description="已卸载实例 ID。")
    file_name: str = Field(alias="fileName", description="已卸载文件名。")


FadeMode = Literal["linear", "easeIn", "easeOut", "easeBoth", "overshoot", "zip"]


class ItemMove(VTSBaseModel):
    """单个道具移动参数。"""

    item_instance_id: str = Field(alias="itemInstanceID", description="道具实例 ID。")
    time_in_seconds: float = Field(
        alias="timeInSeconds",
        ge=0,
        le=30,
        description="过渡耗时秒数。",
    )
    fade_mode: FadeMode = Field(alias="fadeMode", description="移动插值模式。")
    position_x: float = Field(
        alias="positionX",
        description="目标 X 坐标，<= -1000 表示忽略。",
    )
    position_y: float = Field(
        alias="positionY",
        description="目标 Y 坐标，<= -1000 表示忽略。",
    )
    size: float = Field(description="目标尺寸，<= -1000 表示忽略。")
    rotation: float = Field(description="目标旋转角度，<= -1000 表示忽略。")
    order: int = Field(description="目标排序层，<= -1000 表示忽略。")
    set_flip: bool = Field(alias="setFlip", description="是否应用翻转状态。")
    flip: bool = Field(description="目标翻转状态。")
    user_can_stop: bool = Field(
        alias="userCanStop",
        description="用户拖拽时是否可中断移动。",
    )


class MovedItemResult(VTSBaseModel):
    """道具移动结果。"""

    item_instance_id: str = Field(alias="itemInstanceID", description="道具实例 ID。")
    success: bool = Field(description="该道具是否移动成功。")
    error_id: int = Field(alias="errorID", description="失败时的错误 ID，成功为 -1。")


class PinInfo(VTSBaseModel):
    """道具固定到模型的详细定位信息。"""

    model_id: str = Field(
        alias="modelID",
        description="目标模型 ID；为空时使用当前模型。",
    )
    art_mesh_id: str = Field(
        alias="artMeshID",
        description="目标 ArtMesh ID；为空时随机。",
    )
    angle: float = Field(description="目标角度。")
    size: float = Field(description="目标大小。")
    vertex_id1: int = Field(alias="vertexID1", description="三角形顶点 1。")
    vertex_id2: int = Field(alias="vertexID2", description="三角形顶点 2。")
    vertex_id3: int = Field(alias="vertexID3", description="三角形顶点 3。")
    vertex_weight1: float = Field(alias="vertexWeight1", description="顶点 1 权重。")
    vertex_weight2: float = Field(alias="vertexWeight2", description="顶点 2 权重。")
    vertex_weight3: float = Field(alias="vertexWeight3", description="顶点 3 权重。")


class ArtMeshHitInfo(PinInfo):
    """命中的 ArtMesh 详细信息。"""


class ArtMeshHit(VTSBaseModel):
    """一次模型点击命中的 ArtMesh 信息。"""

    art_mesh_order: int = Field(
        alias="artMeshOrder",
        description="在命中点处的 ArtMesh 层级顺序，0 为最上层。",
    )
    is_masked: bool = Field(alias="isMasked", description="该 ArtMesh 是否被遮罩。")
    hit_info: ArtMeshHitInfo = Field(
        alias="hitInfo",
        description="ArtMesh 命中详情与重心坐标。",
    )


class PostProcessingValue(VTSBaseModel):
    """单个后处理配置项更新。"""

    config_id: str = Field(alias="configID", description="配置项 ID，可大小写不敏感。")
    config_value: str = Field(
        alias="configValue",
        description="配置项值，始终以字符串形式发送。",
    )


class PostProcessingConfigEntry(VTSBaseModel):
    """后处理配置项状态。"""

    internal_id: str = Field(alias="internalID", description="内部配置 ID。")
    enum_id: str = Field(alias="enumID", description="枚举风格配置 ID。")
    explanation: str = Field(description="配置项说明。")
    type: str = Field(description="配置项类型。")
    activation_config: bool = Field(
        alias="activationConfig",
        description="是否为激活效果的关键配置。",
    )
    float_value: float = Field(alias="floatValue", description="浮点值。")
    float_min: float = Field(alias="floatMin", description="浮点最小值。")
    float_max: float = Field(alias="floatMax", description="浮点最大值。")
    float_default: float = Field(alias="floatDefault", description="浮点默认值。")
    int_value: int = Field(alias="intValue", description="整数值。")
    int_min: int = Field(alias="intMin", description="整数最小值。")
    int_max: int = Field(alias="intMax", description="整数最大值。")
    int_default: int = Field(alias="intDefault", description="整数默认值。")
    color_value: str = Field(alias="colorValue", description="RGBA 十六进制颜色值。")
    color_default: str = Field(alias="colorDefault", description="默认颜色值。")
    color_has_alpha: bool = Field(
        alias="colorHasAlpha",
        description="颜色配置是否支持透明度。",
    )
    bool_value: bool = Field(alias="boolValue", description="布尔值。")
    bool_default: bool = Field(alias="boolDefault", description="默认布尔值。")
    string_value: str = Field(alias="stringValue", description="字符串值。")
    string_default: str = Field(alias="stringDefault", description="默认字符串值。")
    scene_item_value: str = Field(alias="sceneItemValue", description="场景道具值。")
    scene_item_default: str = Field(
        alias="sceneItemDefault",
        description="默认场景道具值。",
    )


class PostProcessingEffect(VTSBaseModel):
    """后处理效果。"""

    internal_id: str = Field(alias="internalID", description="内部效果 ID。")
    enum_id: str = Field(alias="enumID", description="枚举风格效果 ID。")
    explanation: str = Field(description="效果说明。")
    effect_is_active: bool = Field(
        alias="effectIsActive",
        description="效果是否正在生效。",
    )
    effect_is_restricted: bool = Field(
        alias="effectIsRestricted",
        description="是否为受限/实验性效果。",
    )
    config_entries: list[PostProcessingConfigEntry] = Field(
        alias="configEntries",
        description="该效果的全部配置项。",
    )

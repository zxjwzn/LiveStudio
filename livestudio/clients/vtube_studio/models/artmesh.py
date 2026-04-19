"""ArtMesh and scene color related request/response models."""

from __future__ import annotations

from pydantic import Field

from .base import VTSEmptyData, VTSRequestEnvelope, VTSResponseEnvelope
from .common import ArtMeshMatcher, CapturePart, ColorTint


class ArtMeshListRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取当前模型的 ArtMesh 列表。"""

    message_type: str = Field(default="ArtMeshListRequest", alias="messageType", description="请求当前模型所有 ArtMesh 名称与标签。")
    data: VTSEmptyData = Field(default_factory=VTSEmptyData, description="该请求无需额外参数。")


class ArtMeshListResponseData(VTSEmptyData):
    """ArtMesh 列表响应。"""

    model_loaded: bool = Field(alias="modelLoaded", description="当前是否加载模型。")
    number_of_art_mesh_names: int = Field(alias="numberOfArtMeshNames", description="ArtMesh 名称数量。")
    number_of_art_mesh_tags: int = Field(alias="numberOfArtMeshTags", description="ArtMesh 标签数量。")
    art_mesh_names: list[str] = Field(alias="artMeshNames", description="ArtMesh ID 列表。")
    art_mesh_tags: list[str] = Field(alias="artMeshTags", description="全部唯一标签列表。")


class ArtMeshListResponse(VTSResponseEnvelope[ArtMeshListResponseData]):
    """ArtMesh 列表响应信封。"""


class ColorTintRequestData(VTSEmptyData):
    """为 ArtMesh 应用颜色覆盖。"""

    color_tint: ColorTint = Field(alias="colorTint", description="目标颜色覆盖设置。")
    art_mesh_matcher: ArtMeshMatcher = Field(alias="artMeshMatcher", description="匹配 ArtMesh 的筛选规则。")


class ColorTintRequest(VTSRequestEnvelope[ColorTintRequestData]):
    """ArtMesh 着色请求。"""

    message_type: str = Field(default="ColorTintRequest", alias="messageType", description="请求为匹配的 ArtMesh 应用颜色。")


class ColorTintResponseData(VTSEmptyData):
    """ArtMesh 着色响应。"""

    matched_art_meshes: int = Field(alias="matchedArtMeshes", description="本次匹配并应用的 ArtMesh 数量。")


class ColorTintResponse(VTSResponseEnvelope[ColorTintResponseData]):
    """ArtMesh 着色响应信封。"""


class SceneColorOverlayInfoRequest(VTSRequestEnvelope[VTSEmptyData]):
    """获取场景采样光照信息。"""

    message_type: str = Field(default="SceneColorOverlayInfoRequest", alias="messageType", description="请求当前场景光照叠加配置。")
    data: VTSEmptyData = Field(default_factory=VTSEmptyData, description="该请求无需额外参数。")


class SceneColorOverlayInfoResponseData(VTSEmptyData):
    """场景光照叠加响应。"""

    active: bool = Field(description="场景光照叠加是否开启。")
    items_included: bool = Field(alias="itemsIncluded", description="是否同时影响道具。")
    is_window_capture: bool = Field(alias="isWindowCapture", description="是否为窗口采样。")
    base_brightness: int = Field(alias="baseBrightness", description="基础亮度。")
    color_boost: int = Field(alias="colorBoost", description="颜色增强。")
    smoothing: int = Field(description="平滑值。")
    color_overlay_r: int = Field(alias="colorOverlayR", description="最终叠加红色值。")
    color_overlay_g: int = Field(alias="colorOverlayG", description="最终叠加绿色值。")
    color_overlay_b: int = Field(alias="colorOverlayB", description="最终叠加蓝色值。")
    color_avg_r: int = Field(alias="colorAvgR", description="平均红色值。")
    color_avg_g: int = Field(alias="colorAvgG", description="平均绿色值。")
    color_avg_b: int = Field(alias="colorAvgB", description="平均蓝色值。")
    left_capture_part: CapturePart = Field(alias="leftCapturePart", description="左侧采样区域。")
    middle_capture_part: CapturePart = Field(alias="middleCapturePart", description="中间采样区域。")
    right_capture_part: CapturePart = Field(alias="rightCapturePart", description="右侧采样区域。")


class SceneColorOverlayInfoResponse(VTSResponseEnvelope[SceneColorOverlayInfoResponseData]):
    """场景光照叠加响应信封。"""

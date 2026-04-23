"""VTube Studio API 共用的 Pydantic 基础模型。"""

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

RequestDataT = TypeVar("RequestDataT", bound=BaseModel)
ResponseDataT = TypeVar("ResponseDataT", bound=BaseModel)


class VTSBaseModel(BaseModel):
    """所有 API 模型的公共基类。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class VTSRequestEnvelope(VTSBaseModel, Generic[RequestDataT]):
    """请求信封。"""

    api_name: str = Field(
        default="VTubeStudioPublicAPI",
        alias="apiName",
        description="固定 API 名称，所有请求必须为 `VTubeStudioPublicAPI`。",
    )
    api_version: str = Field(
        default="1.0",
        alias="apiVersion",
        description="API 版本号，当前公开文档为 `1.0`。",
    )
    request_id: str = Field(
        default_factory=lambda: uuid4().hex,
        alias="requestID",
        min_length=1,
        max_length=64,
        description="请求唯一标识。建议每次请求都提供，便于匹配响应与排障。",
    )
    message_type: str = Field(
        alias="messageType",
        description="请求消息类型，例如 `StatisticsRequest`。",
    )
    data: RequestDataT = Field(
        description="请求负载。即使某些接口不需要，发送空对象通常也会被服务端忽略。",
    )

    def to_payload(self) -> dict[str, Any]:
        """将模型转换为适合发送的 JSON 负载。"""

        return self.model_dump(by_alias=True, exclude_none=True)


class VTSResponseEnvelope(VTSBaseModel, Generic[ResponseDataT]):
    """响应信封。"""

    api_name: str = Field(alias="apiName", description="固定 API 名称。")
    api_version: str = Field(alias="apiVersion", description="响应的 API 版本。")
    timestamp: int = Field(description="服务端处理该请求时的 UNIX 毫秒时间戳。")
    message_type: str = Field(
        alias="messageType",
        description="响应消息类型，例如 `StatisticsResponse`。",
    )
    request_id: str = Field(alias="requestID", description="与请求对应的唯一标识。")
    data: ResponseDataT = Field(description="响应业务负载。")


class VTSEmptyData(VTSBaseModel):
    """空数据载荷。"""


class VTSFlexibleData(BaseModel):
    """允许保留未知字段的数据载荷。"""

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class VTSAPIErrorData(VTSBaseModel):
    """VTS `APIError` 响应的数据负载。"""

    error_id: int = Field(alias="errorID", description="VTube Studio 定义的错误编号。")
    message: str = Field(description="错误说明文本。")


class VTSAPIErrorEnvelope(VTSBaseModel):
    """`APIError` 响应信封。"""

    api_name: str = Field(alias="apiName", description="固定 API 名称。")
    api_version: str = Field(alias="apiVersion", description="响应的 API 版本。")
    timestamp: int = Field(description="服务端处理请求时的 UNIX 毫秒时间戳。")
    message_type: str = Field(alias="messageType", description="固定为 `APIError`。")
    request_id: str = Field(alias="requestID", description="与请求对应的唯一标识。")
    data: VTSAPIErrorData = Field(description="错误负载。")

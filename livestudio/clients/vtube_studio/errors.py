"""VTube Studio exception hierarchy."""

from __future__ import annotations

from typing import Any


class VTubeStudioError(Exception):
    """VTube Studio 客户端基础异常。"""


class VTubeStudioConnectionError(ConnectionError, VTubeStudioError):
    """连接建立、关闭或底层传输失败。"""


class ResponseError(VTubeStudioError):
    """请求超时、响应格式不正确或无法匹配请求。"""


class APIError(VTubeStudioError):
    """VTube Studio 返回 `APIError` 消息。"""

    def __init__(self, error_id: int, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(f"VTube Studio API error {error_id}: {message}")
        self.error_id = error_id
        self.message = message
        self.payload = payload or {}


class AuthenticationError(VTubeStudioError):
    """鉴权失败。"""

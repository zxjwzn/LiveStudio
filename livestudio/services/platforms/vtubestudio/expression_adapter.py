"""VTube Studio 原生表情触发适配器"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

from livestudio.clients.vtube_studio.models import (
    ExpressionActivationRequest,
    ExpressionActivationRequestData,
)
from livestudio.services.expression.models import NativeExpressionTrigger
from livestudio.utils.log import logger

PLATFORM_NAME = "vtubestudio"


class _ExpressionClient(Protocol):
    """适配器只依赖客户端的表情激活能力"""

    async def set_expression_active(
        self, request: ExpressionActivationRequest
    ) -> object: ...


class VTSExpressionAdapter:
    """把平台无关的 NativeExpressionTrigger 翻译为 VTS 表情激活/停用调用

    职责：
    1. 维护 native_ref（表情名）到 .exp3.json 文件名的映射。
    2. 记录当前已激活的表情文件，每次 apply 时与目标集合 diff，
       只对变化的表情发送 set_expression_active。
    """

    def __init__(self, name_to_file: Mapping[str, str] | None = None) -> None:
        self._name_to_file: dict[str, str] = dict(name_to_file or {})
        self._active_files: set[str] = set()

    @property
    def active_files(self) -> frozenset[str]:
        """返回当前已激活的表情文件集合快照"""

        return frozenset(self._active_files)

    def _resolve_file(self, native_ref: str) -> str | None:
        """把 native_ref 解析为 .exp3.json 文件名

        native_ref 既可以是模型配置里的表情名，也可以直接是 .exp3.json 文件名。
        无法解析时返回 None。
        """

        mapped = self._name_to_file.get(native_ref)
        if mapped is not None:
            return mapped
        if native_ref.endswith(".exp3.json"):
            return native_ref
        return None

    async def apply(
        self,
        triggers: Iterable[NativeExpressionTrigger],
        client: _ExpressionClient,
        *,
        fade_time: float | None = None,
    ) -> None:
        """diff 目标表情集合与当前激活集合，只对变化项调用 VTS API

        fade_time 为本次调用的淡入/淡出时长，传 None 时由 VTS 用其默认值。
        VTS 接受范围 [0, 2]，会自动钳位。
        """

        wanted_files: set[str] = set()
        for trigger in triggers:
            if trigger.platform != PLATFORM_NAME:
                continue
            resolved = self._resolve_file(trigger.native_ref)
            if resolved is None:
                logger.warning("无法解析 VTS 表情引用，已跳过: {}", trigger.native_ref)
                continue
            wanted_files.add(resolved)

        to_deactivate = self._active_files - wanted_files
        to_activate = wanted_files - self._active_files

        # 逐项更新内部激活集：成功停用即 discard、成功激活即 add。
        # 若某次 _set_active 抛异常中断循环，内部记录仍与 VTS 实际状态一致，
        # 下次 diff 不会算错（整体赋值 self._active_files = wanted_files 在异常时会漂移）。
        for expression_file in sorted(to_deactivate):
            await self._set_active(
                client, expression_file, active=False, fade_time=fade_time
            )
            self._active_files.discard(expression_file)
        for expression_file in sorted(to_activate):
            await self._set_active(
                client, expression_file, active=True, fade_time=fade_time
            )
            self._active_files.add(expression_file)

    async def _set_active(
        self,
        client: _ExpressionClient,
        expression_file: str,
        *,
        active: bool,
        fade_time: float | None,
    ) -> None:
        clamped = None if fade_time is None else max(0.0, min(2.0, fade_time))
        await client.set_expression_active(
            ExpressionActivationRequest(
                data=ExpressionActivationRequestData(
                    expressionFile=expression_file,
                    fadeTime=clamped,
                    active=active,
                ),
            ),
        )

"""VTube Studio 原生表情触发适配器"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

from livestudio.clients.vtube_studio.models import (
    ExpressionActivationRequest,
    ExpressionActivationRequestData,
)
from livestudio.services.animations.constants import DEFAULT_NATIVE_SCOPE
from livestudio.services.expression.models import NativeExpressionTrigger
from livestudio.utils.log import logger

from .constants import PLATFORM_NAME


class _ExpressionClient(Protocol):
    """适配器只依赖客户端的表情激活能力"""

    async def set_expression_active(
        self, request: ExpressionActivationRequest
    ) -> object: ...


class VTSExpressionAdapter:
    """把平台无关的 NativeExpressionTrigger 翻译为 VTS 表情激活/停用调用

    职责：
    1. 维护 native_ref（表情名）到 .exp3.json 文件名的映射。
    2. 按「作用域(scope)」分别记录各来源想要激活的表情文件，每次 apply 只
       更新该作用域的期望集，再把所有作用域的并集与 VTS 实际激活集 diff，
       只对变化的表情发送 set_expression_active。

    分作用域是为了让互相独立的来源（情绪解算的临时触发 vs 仪表盘手动 toggle
    的常驻表情）互不干扰：情绪解算收尾把自己那一组清空时，不会误关用户手动
    点亮的常驻表情，反之亦然。
    """

    def __init__(self, name_to_file: Mapping[str, str] | None = None) -> None:
        self._name_to_file: dict[str, str] = dict(name_to_file or {})
        # 各作用域当前想要激活的文件集；VTS 实际激活集 = 所有作用域的并集。
        self._scoped_files: dict[str, set[str]] = {}
        self._active_files: set[str] = set()

    @property
    def active_files(self) -> frozenset[str]:
        """返回当前已激活的表情文件集合快照（所有作用域并集）"""

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
        scope: str = DEFAULT_NATIVE_SCOPE,
    ) -> None:
        """更新某作用域的期望表情集，再把所有作用域并集与实际激活集 diff

        只对变化项调用 VTS API。scope 区分不同来源（如情绪解算与手动 toggle），
        各来源只覆盖自己那一组期望，互不影响其它来源已点亮的表情。

        fade_time 为本次调用的淡入/淡出时长，传 None 时由 VTS 用其默认值。
        VTS 接受范围 [0, 2]，会自动钳位。
        """

        scope_files: set[str] = set()
        for trigger in triggers:
            if trigger.platform != PLATFORM_NAME:
                continue
            resolved = self._resolve_file(trigger.native_ref)
            if resolved is None:
                logger.warning("无法解析 VTS 表情引用，已跳过: {}", trigger.native_ref)
                continue
            scope_files.add(resolved)

        if scope_files:
            self._scoped_files[scope] = scope_files
        else:
            self._scoped_files.pop(scope, None)

        wanted_files: set[str] = set()
        for files in self._scoped_files.values():
            wanted_files |= files

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

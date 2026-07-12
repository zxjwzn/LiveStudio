"""各平台都能用的表情解算控制器"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

from livestudio.services.animations.constants import EMOTION_NATIVE_SCOPE
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.expression import (
    EmotionKind,
    ExpressionHistory,
    ExpressionProfileConfig,
    ExpressionRequest,
    ExpressionSolver,
    ExpressionUnit,
    ResolvedSemanticTarget,
    SelectedExpression,
    SemanticExpressionUnit,
)
from livestudio.services.semantic_actions import (
    SemanticTweenRequest,
    neutral_value,
)
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import ExpressionControllerSettings
from ..constants import EXPRESSION_AU_PRIORITY, EXPRESSION_NEUTRAL_PRIORITY
from ..models import AnimationType

# 外部释放 hold 时超长占权时长;实际由 release 时 duration=0 同优先级瞬时 tween 收口。
_EXTERNAL_HOLD_SECONDS = 24 * 3600.0


class ExpressionController(AnimationController[ExpressionControllerSettings]):
    """解算并下发情绪表情。

    生命周期:
      过渡(au_priority) → 保持 → **fire end** → 清 EMOTION native → 回归(neutral_priority)

    end 锚点语义(与 MCP 文档一致):「开始回中性时」,脸上可能仍在回落。
    因此 end 在 hold 退出后立刻触发,恢复在后台继续,不阻塞时间线 Job。

    hold_duration=None: 外部释放模式。release_hold() 只 set 信号,不 cancel _drive、
    不等待恢复——恢复仍由同一 _drive 在 fire end 之后自然跑完。

    新表情/仪表盘连点: start() 可重入,硬打断上一段后立刻开新表情。
    硬打断 cancel _drive,快照后异步清理(因原 _drive 已不能继续)。
    """

    def __init__(
        self,
        runtime: PlatformAnimationRuntime,
        name: str,
        config: ExpressionControllerSettings,
        profile: ExpressionProfileConfig,
    ) -> None:
        super().__init__(runtime, name, config)
        self._profile = profile
        self._solver = ExpressionSolver(
            units=self._resolvable_units(profile.to_units()),
            rules=profile.to_rules(),
            history=ExpressionHistory(capacity=config.history_capacity),
            top_candidates=config.top_candidates,
            typicality_floor=config.typicality_floor,
            typicality_power=config.typicality_power,
        )
        self._finishing_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._active_semantic_targets: list[ResolvedSemanticTarget] = []
        self._active_native_triggers: list = []
        self._emotion_listeners: list[tuple[Callable[[], None], Callable[[], None]]] = []
        self._emotion_start_fired = False
        self._emotion_end_fired = False
        self._hold_release = asyncio.Event()

    @property
    def animation_type(self) -> AnimationType:
        return AnimationType.ONESHOT

    @property
    def solver(self) -> ExpressionSolver:
        return self._solver

    def _resolvable_units(self, units: list[ExpressionUnit]) -> list[ExpressionUnit]:
        adapter = self.runtime.platform.semantic_adapter
        if adapter is None:
            return units
        result: list[ExpressionUnit] = []
        for unit in units:
            if not isinstance(unit, SemanticExpressionUnit):
                result.append(unit)
                continue
            unresolved = [t.action for t in unit.targets if not adapter.can_resolve(t.action)]
            if unresolved:
                logger.debug(
                    "AU 候选预过滤: id={}, 原因=语义动作未绑定, actions={}",
                    unit.id,
                    [a.value for a in unresolved],
                )
                continue
            result.append(unit)
        return result

    @property
    def finishing_task(self) -> asyncio.Task[None] | None:
        return self._finishing_task

    async def start(self, **kwargs: object) -> bool:
        """ONESHOT 可重入:新请求立刻打断旧请求。"""

        await self._interrupt_previous()
        async with self._lifecycle_lock:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run(**kwargs))
            return True

    async def _interrupt_previous(self) -> None:
        async with self._lifecycle_lock:
            task = self._task
            self._task = None
            self._stop_event.set()
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._cancel_finishing()

    def bind_emotion_anchors(
        self,
        on_start: Callable[[], None],
        on_end: Callable[[], None],
    ) -> Callable[[], None]:
        pair = (on_start, on_end)
        self._emotion_listeners.append(pair)

        def _unbind() -> None:
            with contextlib.suppress(ValueError):
                self._emotion_listeners.remove(pair)

        return _unbind

    def _fire_emotion_start(self) -> None:
        if self._emotion_start_fired:
            return
        self._emotion_start_fired = True
        for on_start, _ in list(self._emotion_listeners):
            with contextlib.suppress(Exception):
                on_start()

    def _fire_emotion_end(self) -> None:
        if self._emotion_end_fired:
            return
        if not self._emotion_start_fired:
            return
        self._emotion_end_fired = True
        for _, on_end in list(self._emotion_listeners):
            with contextlib.suppress(Exception):
                on_end()

    async def execute(self, **kwargs: object) -> None:
        emotion = self._coerce_emotion(kwargs.get("emotion"))
        if emotion is None:
            logger.warning("表情控制器未收到合法 emotion，跳过")
            return

        intensity = self._coerce_intensity(kwargs.get("intensity"))
        transition_duration = self._coerce_duration(
            kwargs.get("transition_duration"),
            self.config.transition_duration,
        )
        if "hold_duration" not in kwargs:
            hold_duration: float | None = self.config.hold_duration
        elif kwargs.get("hold_duration") is None:
            hold_duration = None
        else:
            hold_duration = self._coerce_duration(kwargs.get("hold_duration"), self.config.hold_duration)

        await self._cancel_finishing()
        self._emotion_start_fired = False
        self._emotion_end_fired = False
        self._hold_release = asyncio.Event()

        selected = self._solver.solve(ExpressionRequest(emotion=emotion, intensity=intensity))
        self._active_semantic_targets = list(selected.semantic_targets)
        self._active_native_triggers = list(selected.native_triggers)

        await self.runtime.platform.apply_native_expressions(
            selected.native_triggers,
            fade_time=transition_duration,
            scope=EMOTION_NATIVE_SCOPE,
        )
        self._fire_emotion_start()

        if selected.semantic_targets or selected.native_triggers or hold_duration is None:
            self._finishing_task = asyncio.create_task(
                self._drive(selected, transition_duration, hold_duration),
            )
        else:
            self._fire_emotion_end()

        logger.info(
            "表情解算: 情绪={}, AU={}, 语义目标={}, 原生触发={}, hold={}",
            emotion,
            [u.id for u in selected.units],
            len(selected.semantic_targets),
            len(selected.native_triggers),
            "external" if hold_duration is None else hold_duration,
        )

    async def release_hold(self) -> None:
        """协作结束外部 hold:只发信号。

        不 cancel _drive、不等待恢复。_drive 在 hold 退出后先 fire end(时间线可完成
        事件/Job),再继续清 native + priority-0 回归。
        """

        self._hold_release.set()

    async def _drive(
        self,
        selected: SelectedExpression,
        transition_duration: float,
        hold_duration: float | None,
    ) -> None:
        """过渡 → 保持 → fire end → 清 native → priority-0 回归。"""

        try:
            await self._play_hold_phase(selected, transition_duration, hold_duration)
            # hold 结束 = 表演语义结束;恢复不阻塞时间线
            self._fire_emotion_end()
            await self._restore_phase(selected, transition_duration)
        except asyncio.CancelledError:
            # 硬打断:end 若未发则补发;参数清理由 _cancel_finishing 快照负责
            self._fire_emotion_end()
            raise
        finally:
            if self._finishing_task is asyncio.current_task():
                self._finishing_task = None

    async def _play_hold_phase(
        self,
        selected: SelectedExpression,
        transition_duration: float,
        hold_duration: float | None,
    ) -> None:
        """过渡到目标并保持,直到时长到点或 release_hold。

        有语义目标: 过渡 tween + 保持(长 tween 占权 / 定时 / 外部释放)。
        无语义(纯 native 或空): 过渡 sleep 后按 hold 等待,不占 AU 优先级。
        """

        if selected.semantic_targets:
            await self._tween_targets(selected.semantic_targets, transition_duration)
            if hold_duration is None:
                await self._hold_until_release(selected.semantic_targets)
            elif hold_duration > 0:
                await self._tween_targets(
                    selected.semantic_targets,
                    hold_duration,
                    easing="linear",
                )
            return

        # 纯 native / 空内容:没有 AU 可占权,只计时
        if hold_duration is None:
            if transition_duration > 0:
                await asyncio.sleep(transition_duration)
            await self._hold_release.wait()
        else:
            total = transition_duration + hold_duration
            if total > 0:
                await asyncio.sleep(total)

    async def _restore_phase(
        self,
        selected: SelectedExpression,
        transition_duration: float,
    ) -> None:
        """清 EMOTION native + AU 回归静息。在 fire end 之后调用。"""

        if selected.native_triggers:
            await self.runtime.platform.apply_native_expressions(
                [],
                fade_time=transition_duration,
                scope=EMOTION_NATIVE_SCOPE,
            )
            self._active_native_triggers = []

        if selected.semantic_targets:
            await self._tween_targets(
                [
                    ResolvedSemanticTarget(
                        action=driven.action,
                        value=neutral_value(driven.action),
                        easing=driven.easing,
                    )
                    for driven in selected.semantic_targets
                ],
                self.config.neutral_transition_duration,
                priority=EXPRESSION_NEUTRAL_PRIORITY,
            )
        self._active_semantic_targets = []

    async def _hold_until_release(self, targets: list[ResolvedSemanticTarget]) -> None:
        """超长 tween 占权;release 后瞬时同优先级收口,再返回(由 _drive 发 end 并恢复)。"""

        hold_task = asyncio.create_task(
            self._tween_targets(targets, _EXTERNAL_HOLD_SECONDS, easing="linear"),
            name="expression-external-hold",
        )
        try:
            await self._hold_release.wait()
        finally:
            # 先 cancel hold_task,确保长 tween 一定被收回(即便本协程被 cancel)
            if not hold_task.done():
                hold_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await hold_task
            # 瞬时同优先级收口,清理长 tween 留下的占权
            with contextlib.suppress(Exception):
                await self._tween_targets(targets, 0.0, easing="linear")

    async def _tween_targets(
        self,
        targets: list[ResolvedSemanticTarget],
        duration: float,
        *,
        easing: str | None = None,
        priority: int | None = None,
    ) -> None:
        if not targets:
            return
        resolved_priority = EXPRESSION_AU_PRIORITY if priority is None else priority
        await self.runtime.platform.tween_semantic(
            [
                SemanticTweenRequest(
                    action_parameter_name=target.action,
                    end_value=target.value,
                    duration=duration,
                    easing=easing if easing is not None else target.easing,
                    priority=resolved_priority,
                )
                for target in targets
            ]
        )

    async def _cleanup_snapshot(
        self,
        natives: list,
        driven: list[ResolvedSemanticTarget],
        *,
        fade_time: float,
    ) -> None:
        """硬打断清理:用 cancel 前快照清 native + AU 回归。"""

        if natives:
            with contextlib.suppress(Exception):
                await self.runtime.platform.apply_native_expressions(
                    [],
                    fade_time=fade_time,
                    scope=EMOTION_NATIVE_SCOPE,
                )
        if not driven:
            return
        targets = [
            ResolvedSemanticTarget(
                action=item.action,
                value=neutral_value(item.action),
                easing=item.easing,
            )
            for item in driven
        ]
        with contextlib.suppress(Exception):
            await self._tween_targets(
                targets,
                self.config.neutral_transition_duration,
                priority=EXPRESSION_NEUTRAL_PRIORITY,
            )

    async def _cancel_finishing(self) -> None:
        """硬打断:cancel _drive,快照后后台清理(新表情/stop/cancel)。"""

        natives = list(self._active_native_triggers)
        driven = list(self._active_semantic_targets)
        fade = float(self.config.transition_duration)

        # 先 cancel _drive 再做后续:避免 set(_hold_release) 在前导致 cancel 丢失、
        # _drive 照常跑 _restore_phase 同时 cleanup 又发一遍 neutral(双重回归)。
        task = self._finishing_task
        self._finishing_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._fire_emotion_end()
        self._active_native_triggers = []
        self._active_semantic_targets = []
        if natives or driven:
            # 存引用,防止 fire-and-forget 任务被 GC 掉导致回归请求发不出去
            self._cleanup_task = asyncio.create_task(
                self._cleanup_snapshot(natives, driven, fade_time=fade),
                name="expression-interrupt-cleanup",
            )

    async def stop(self) -> None:
        """硬停止:取消 _drive 并用快照清理。正常 end 约束请用 release_hold。"""

        await self._cancel_finishing()
        await super().stop()

    async def cancel(self) -> None:
        await self._cancel_finishing()
        await super().cancel()

    @staticmethod
    def _coerce_emotion(value: object) -> EmotionKind | None:
        if isinstance(value, EmotionKind):
            return value
        if isinstance(value, str):
            try:
                return EmotionKind(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _coerce_intensity(value: object) -> float:
        if isinstance(value, bool):
            return 1.0
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        return 1.0

    @staticmethod
    def _coerce_duration(value: object, fallback: float) -> float:
        if isinstance(value, bool):
            return fallback
        if isinstance(value, (int, float)):
            return max(0.0, float(value))
        return fallback

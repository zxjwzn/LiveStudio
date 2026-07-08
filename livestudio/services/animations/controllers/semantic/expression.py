"""各平台都能用的表情解算控制器"""

import asyncio
import contextlib

from livestudio.services.animations.constants import EMOTION_NATIVE_SCOPE
from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.expression import (
    EmotionKind,
    ExpressionHistory,
    ExpressionProfileConfig,
    ExpressionRequest,
    ExpressionSolver,
    ResolvedSemanticTarget,
    SelectedExpression,
)
from livestudio.services.semantic_actions import (
    SemanticAction,
    SemanticTweenRequest,
    neutral_value,
    semantic_actions_overlap,
)
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import ExpressionControllerSettings
from ..models import AnimationType


class ExpressionController(AnimationController[ExpressionControllerSettings]):
    """接收单个情绪，调用表情解算层产出并下发一套表情

    宿主表情解算器（ExpressionSolver）。每次 execute 接收一个 EmotionKind，
    解算出一套 AU 组合：

    - execute 本身只做「快动作」：解算 + 激活原生表情（fade 与过渡时长一致），
      然后把「过渡缓动 → 保持 → 收尾停用原生」丢进后台任务，立即返回，不阻塞调用方。
    - 后台任务串行 await 过渡段与保持段缓动（合计 transition + hold 秒），结束后
      apply([]) 停用本次激活的原生表情。无语义目标时改用 sleep 计时。
    - 新的 execute 进来时，先取消上一个尚未结束的后台任务，避免旧任务到点
      apply([]) 把本次新激活的原生表情误停。语义参数的交接由 tween engine
      负责：同优先级的新过渡段会直接接管旧保持段占用的参数，无需手动释放。
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
            units=profile.to_units(),
            rules=profile.to_rules(),
            history=ExpressionHistory(capacity=config.history_capacity),
            top_candidates=config.top_candidates,
            typicality_floor=config.typicality_floor,
            typicality_power=config.typicality_power,
        )
        self._finishing_task: asyncio.Task[None] | None = None
        # 上一次表情驱动过的语义动作集合：新表情若不再覆盖其中某些动作，
        # 需把它们一并拉回静息，避免旧表情参数被遗弃在原位。
        self._last_actions: set[SemanticAction] = set()

    @property
    def animation_type(self) -> AnimationType:
        """一次性控制器：每次 execute 触发一套表情"""

        return AnimationType.ONESHOT

    @property
    def solver(self) -> ExpressionSolver:
        """返回内部表情解算器"""

        return self._solver

    @property
    def finishing_task(self) -> asyncio.Task[None] | None:
        """返回当前后台收尾任务（过渡+保持+停用），无则 None"""

        return self._finishing_task

    async def execute(self, **kwargs: object) -> None:
        """根据传入的单个情绪解算并应用表情，快返回。

        kwargs:
            emotion: EmotionKind | str，本次要表达的情绪
            intensity: float，可选，表情强度 [0,1]，缺省 1.0；0 时全脸回归 neutral
        """

        emotion = self._coerce_emotion(kwargs.get("emotion"))
        if emotion is None:
            logger.warning("表情控制器未收到合法 emotion，跳过")
            return

        intensity = self._coerce_intensity(kwargs.get("intensity"))

        # 先取消上一次尚未结束的收尾任务，避免它到点 apply([]) 停用本次要激活
        # 的原生表情。语义参数交给 engine 同优先级接管，无需在此释放。
        await self._cancel_finishing()

        selected = self._solver.solve(ExpressionRequest(emotion=emotion, intensity=intensity))

        # 把「上一次驱动过、但本次不再覆盖」的动作补成静息目标并入本次表情：
        # 这些参数会随本次过渡段一起从当前值平滑回到 neutral，避免被旧表情遗弃在原位。
        new_actions = {target.action for target in selected.semantic_targets}
        orphaned = {
            old_action
            for old_action in self._last_actions
            if not any(semantic_actions_overlap(old_action, new_action) for new_action in new_actions)
        }
        if orphaned:
            selected.semantic_targets.extend(
                ResolvedSemanticTarget(action=action, value=neutral_value(action)) for action in orphaned
            )
        # 记录本次实际驱动的全部动作（含补入的静息回归），供下一次解算计算差集。
        self._last_actions = {target.action for target in selected.semantic_targets}

        # 原生表情立即激活，淡入时长与语义过渡一致。diff 会顺带停用上一次
        # 仍激活、但本次不再需要的原生表情。
        await self.runtime.platform.apply_native_expressions(
            selected.native_triggers,
            fade_time=self.config.transition_duration,
            scope=EMOTION_NATIVE_SCOPE,
        )

        # 过渡缓动 + 保持 + 收尾停用丢到后台，execute 不阻塞调用方。
        if selected.semantic_targets or selected.native_triggers:
            self._finishing_task = asyncio.create_task(self._drive(selected))

        logger.debug(
            "表情解算: 情绪={}, AU={}, 语义目标={}, 原生触发={}",
            emotion,
            [u.id for u in selected.units],
            len(selected.semantic_targets),
            len(selected.native_triggers),
        )

    async def _drive(self, selected: SelectedExpression) -> None:
        """后台收尾：推进过渡段+保持段缓动，结束后停用原生表情并回归静息。

        流程：过渡 → 保持 → 停用本次原生表情 → （可选）回归静息。
        被取消时（新 execute 到来或控制器停止），级联取消在途缓动任务并释放
        参数，且不会执行后续阶段——新的表情状态由新 execute 接管。
        """

        transition_duration = self.config.transition_duration
        hold_duration = self.config.hold_duration

        if selected.semantic_targets:
            # 过渡段：从当前值缓动到目标值
            await self._tween_targets(selected.semantic_targets, transition_duration)
            # 保持段：停在目标值，期间高优先级持续占用，低优先级缓动无法接管
            if hold_duration > 0:
                await self._tween_targets(selected.semantic_targets, hold_duration, easing="linear")
        else:
            # 纯原生表情：没有语义缓动驱动计时，显式等待整个窗口
            await asyncio.sleep(transition_duration + hold_duration)

        # 收尾：停用本次激活的原生表情（淡出时长与过渡一致）
        if selected.native_triggers:
            await self.runtime.platform.apply_native_expressions(
                [],
                fade_time=transition_duration,
                scope=EMOTION_NATIVE_SCOPE,
            )

        if not selected.semantic_targets:
            return

        # solver 保证同一 action 不会被多个单元重复占用，故 driven 列表 action 无重复。
        targets = [
            ResolvedSemanticTarget(
                action=driven.action,
                value=neutral_value(driven.action),
                easing=driven.easing,
            )
            for driven in selected.semantic_targets
        ]
        await self._tween_targets(targets, self.config.neutral_transition_duration)

    async def _tween_targets(
        self,
        targets: list[ResolvedSemanticTarget],
        duration: float,
        *,
        easing: str | None = None,
    ) -> None:
        """把一组解算目标作为一段语义缓动下发，统一用 config.au_priority。

        easing=None 时各目标用自身 easing；指定时（如保持段）统一覆盖。
        """

        await self.runtime.platform.tween_semantic(
            [
                SemanticTweenRequest(
                    action_parameter_name=target.action,
                    end_value=target.value,
                    duration=duration,
                    easing=easing if easing is not None else target.easing,
                    priority=self.config.au_priority,
                )
                for target in targets
            ]
        )

    async def _cancel_finishing(self) -> None:
        """取消并等待上一个后台收尾任务结束"""

        task = self._finishing_task
        self._finishing_task = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def stop(self) -> None:
        """停止控制器时一并取消后台收尾任务"""

        await self._cancel_finishing()
        self._last_actions.clear()
        await super().stop()

    async def cancel(self) -> None:
        """取消控制器时一并取消后台收尾任务"""

        await self._cancel_finishing()
        self._last_actions.clear()
        await super().cancel()

    @staticmethod
    def _coerce_emotion(value: object) -> EmotionKind | None:
        """把外部传入的情绪值转换为 EmotionKind"""

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
        """把外部传入的强度值转换为 [0,1] 浮点，非法/缺省时回退 1.0"""

        if isinstance(value, bool):  # bool 是 int 子类，需先排除
            return 1.0
        if isinstance(value, (int, float)):
            return max(0.0, min(1.0, float(value)))
        return 1.0

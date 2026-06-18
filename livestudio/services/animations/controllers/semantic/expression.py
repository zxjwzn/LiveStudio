"""各平台都能用的表情解算控制器"""

from livestudio.services.expression import (
    EmotionKind,
    ExpressionHistory,
    ExpressionProfileConfig,
    ExpressionSolver,
)
from livestudio.services.semantic_actions import SemanticTweenRequest
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import ExpressionControllerSettings
from ..models import AnimationType


class ExpressionController(AnimationController[ExpressionControllerSettings]):
    """接收单个情绪，调用表情解算层产出并下发一套表情

    宿主表情解算器（ExpressionSolver）。每次 execute 接收一个 EmotionKind，
    解算出一套 AU 组合，把语义动作目标转成 SemanticTweenRequest 下发给平台，
    把原生表情触发交给平台的 apply_native_expressions。
    """

    def __init__(
        self,
        runtime: "object",  # PlatformAnimationRuntime，避免循环引用注解
        name: str,
        config: ExpressionControllerSettings,
        profile: ExpressionProfileConfig,
    ) -> None:
        super().__init__(runtime, name, config)  # type: ignore[arg-type]
        self._profile = profile
        self._solver = ExpressionSolver(
            units=profile.to_units(),
            rules=profile.to_rules(),
            history=ExpressionHistory(capacity=profile.runtime.history_capacity),
            top_candidates=profile.runtime.top_candidates,
        )

    @property
    def animation_type(self) -> AnimationType:
        """一次性控制器：每次 execute 触发一套表情"""

        return AnimationType.ONESHOT

    @property
    def solver(self) -> ExpressionSolver:
        """返回内部表情解算器"""

        return self._solver

    async def execute(self, **kwargs: object) -> None:
        """根据传入的单个情绪解算并应用表情

        分两段下发语义缓动，都用 config.au_priority：
        1. 过渡段：transition_duration 内从当前值缓动到目标值；
        2. 保持段：hold_duration 内停在目标值，期间高优先级占用，
           低优先级缓动（呼吸/摇摆等）无法接管这些参数。

        kwargs:
            emotion: EmotionKind | str，本次要表达的情绪
        """

        emotion = self._coerce_emotion(kwargs.get("emotion"))
        if emotion is None:
            logger.warning("表情控制器未收到合法 emotion，跳过")
            return

        request = self._profile.build_request(emotion)
        selected = self._solver.solve(request)
        priority = self.config.au_priority

        # 原生表情先触发
        await self.runtime.platform.apply_native_expressions(selected.native_triggers)

        if selected.semantic_targets:
            transition = [
                SemanticTweenRequest(
                    action_parameter_name=target.action,
                    end_value=target.value,
                    duration=request.transition_duration,
                    easing=target.easing,
                    priority=priority,
                )
                for target in selected.semantic_targets
            ]
            await self.runtime.platform.tween_semantic(transition)

            # 保持段：停在目标值，期间持续占用参数
            if request.hold_duration > 0:
                hold = [
                    SemanticTweenRequest(
                        action_parameter_name=target.action,
                        end_value=target.value,
                        duration=request.hold_duration,
                        easing="linear",
                        priority=priority,
                    )
                    for target in selected.semantic_targets
                ]
                await self.runtime.platform.tween_semantic(hold)

        logger.debug(
            "表情解算: 情绪={}, AU={}, 语义目标={}, 原生触发={}",
            emotion,
            [u.id for u in selected.units],
            len(selected.semantic_targets),
            len(selected.native_triggers),
        )

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

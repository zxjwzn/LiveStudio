"""把通用动作的平滑变化换成平台能用的参数变化"""

from collections.abc import Sequence

from livestudio.services.tween import (
    ParameterTweenEngine,
    TweenRequest,
)
from livestudio.utils.log import logger

from .models import (
    _SPEC_BY_ACTION,
    PlatformParameterSpec,
    SemanticAction,
    SemanticActionBinding,
    SemanticActionProfile,
    SemanticTweenRequest,
    clamp_semantic_value,
)


class SemanticActionAdapter:
    """把通用动作换成平台真正要执行的平滑变化

    核心职责:
    1. 接收 list[SemanticTweenRequest]，根据 SemanticActionProfile 和
       PlatformParameterSpec 把语义值线性映射到平台参数值，生成 TweenRequest
       并下发给 ParameterTweenEngine。
    2. 给定一个 SemanticAction，查询其绑定的平台参数当前值，线性反向映射回
       语义动作范围内的值。

    映射是纯线性的范围缩放，缓动曲线只影响 tween engine 的时间插值，
    不参与语义值和平台值之间的数值转换。
    """

    def __init__(
        self,
        profile: SemanticActionProfile,
        *,
        parameter_specs: Sequence[PlatformParameterSpec],
        engine: ParameterTweenEngine,
    ) -> None:
        self._profile = profile
        self._parameter_specs = {spec.name: spec for spec in parameter_specs}
        self._engine = engine
        # 按 action 名建索引方便查找
        self._bindings: dict[str, SemanticActionBinding] = {binding.action.value: binding for binding in profile.bindings}

    # ------------------------------------------------------------------
    # 公开接口: 下发语义缓动请求
    # ------------------------------------------------------------------

    async def apply(self, requests: Sequence[SemanticTweenRequest]) -> None:
        """把一批语义缓动请求转换为平台 TweenRequest 并下发给引擎"""
        tween_requests = self.to_tween_requests(requests)
        if tween_requests:
            await self._engine.tween(tween_requests)

    def to_tween_requests(self, requests: Sequence[SemanticTweenRequest]) -> list[TweenRequest]:
        """把一批语义缓动请求转换为平台 TweenRequest (不下发)"""
        results: list[TweenRequest] = []
        for req in requests:
            results.extend(self._resolve_request(req))
        return results

    # ------------------------------------------------------------------
    # 公开接口: 查询当前语义值
    # ------------------------------------------------------------------

    def query(self, action: SemanticAction | str) -> float | None:
        """查询一个语义动作当前绑定的平台参数，反向映射回语义范围内的值

        读取的是引擎中的瞬时平台参数值，做纯线性范围反映射。
        如果该动作没有绑定或绑定的平台参数都没有活跃状态，返回 None。
        """
        action_str = str(action)
        binding = self._bindings.get(action_str)
        if binding is None:
            return None

        controlled = self._engine.controlled_params
        values: list[float] = []
        for param_name in binding.platform_params:
            spec = self._parameter_specs.get(param_name)
            state = controlled.get(param_name)
            if spec is None or state is None:
                continue
            values.append(_platform_to_semantic(state.value, spec, action_str))

        if not values:
            return None
        first_value = values[0]
        if any(abs(value - first_value) > 1e-4 for value in values[1:]):
            logger.warning(
                "语义动作 {} 绑定参数反查结果不一致: {}",
                action_str,
                values,
            )
        return clamp_semantic_value(action_str, first_value)

    # ------------------------------------------------------------------
    # 内部: 单条请求转换
    # ------------------------------------------------------------------

    def _resolve_request(self, req: SemanticTweenRequest) -> list[TweenRequest]:
        """把一条 SemanticTweenRequest 转换为若干 TweenRequest"""
        binding = self._bindings.get(req.action_parameter_name)
        if binding is None:
            return []

        results: list[TweenRequest] = []

        for param_name in binding.platform_params:
            spec = self._parameter_specs.get(param_name)
            if spec is None:
                continue

            end_value = _semantic_to_platform(req.end_value, spec, req.action_parameter_name)

            # 确定起始值: 请求指定时做映射，否则留 None 让引擎自行决定
            start_value: float | None
            if req.start_value is not None:
                start_value = _semantic_to_platform(req.start_value, spec, req.action_parameter_name)
            else:
                start_value = None
            results.append(
                TweenRequest(
                    parameter_name=param_name,
                    end_value=end_value,
                    start_value=start_value,
                    duration=max(0.0, req.duration),
                    delay=req.delay,
                    easing=req.easing,
                    mode=req.mode,
                    fps=req.fps,
                    priority=req.priority,
                    keep_alive=req.keep_alive,
                )
            )
        return results


# ======================================================================
# 映射函数: 语义值 ↔ 平台值 (纯线性范围缩放)
# ======================================================================


def _semantic_to_platform(
    semantic_value: float,
    spec: PlatformParameterSpec,
    action: str,
) -> float:
    """把语义范围内的值线性映射到平台参数范围

    按 SemanticActionSpec 和平台参数的最小/最大值做线性比例映射。
    结果钳位到平台参数的 [minimum, maximum]。
    """
    semantic_spec = _SPEC_BY_ACTION.get(action)

    if semantic_spec is None:
        # 没有语义规格时，把值当作 [-1, 1] 范围线性映射
        midpoint = _platform_midpoint(spec)
        normalized = max(-1.0, min(1.0, semantic_value))
        if normalized >= 0:
            return _clamp(midpoint + normalized * (spec.maximum - midpoint), spec)
        return _clamp(midpoint + normalized * (midpoint - spec.minimum), spec)

    clamped = max(semantic_spec.minimum, min(semantic_spec.maximum, semantic_value))
    span = semantic_spec.maximum - semantic_spec.minimum
    ratio = 0.0 if span <= 0.0 else (clamped - semantic_spec.minimum) / span
    return _clamp(spec.minimum + ratio * (spec.maximum - spec.minimum), spec)


def _platform_to_semantic(
    platform_value: float,
    spec: PlatformParameterSpec,
    action: str,
) -> float:
    """把平台参数值线性反向映射回语义范围内的值"""
    clamped_pv = max(spec.minimum, min(spec.maximum, platform_value))
    semantic_spec = _SPEC_BY_ACTION.get(action)

    if semantic_spec is None:
        # 没有语义规格时，映射回 [-1, 1]
        midpoint = _platform_midpoint(spec)
        if clamped_pv >= midpoint:
            span = spec.maximum - midpoint
            return 0.0 if span <= 0.0 else (clamped_pv - midpoint) / span
        span = midpoint - spec.minimum
        return 0.0 if span <= 0.0 else -(midpoint - clamped_pv) / span

    span = spec.maximum - spec.minimum
    ratio = 0.0 if span <= 0.0 else (clamped_pv - spec.minimum) / span
    return semantic_spec.minimum + ratio * (semantic_spec.maximum - semantic_spec.minimum)


# ======================================================================
# 工具函数
# ======================================================================


def _platform_midpoint(spec: PlatformParameterSpec) -> float:
    return (spec.minimum + spec.maximum) / 2.0


def _clamp(value: float, spec: PlatformParameterSpec) -> float:
    return max(spec.minimum, min(spec.maximum, value))

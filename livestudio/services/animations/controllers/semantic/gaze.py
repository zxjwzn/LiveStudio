"""各平台都能用的眼神注视控制器

眼睛以中心附近高频轻微扰动为主，偶尔切到随机注视点。头部在 yaw/pitch/roll
三轴上按本周期随机策略跟随、不跟随或反向移动。

仅 gaze_x/y_amplitude、head_follow_strength、head_follow_chance、reverse_head_chance
可由用户配置；其余时长/概率/微扰幅度/均衡窗口已固化为本模块常量，行为不变。
"""

import asyncio
import random
from collections import deque
from typing import Final

from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.semantic_actions import SemanticAction, SemanticTweenRequest
from livestudio.services.tween import Easing, EasingFunction
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import GazeControllerSettings
from ..constants import IDLE_CONTROLLER_PRIORITY
from ..models import AnimationType

# 头部三轴跟随基础因子：head_follow_strength 统一缩放这三者（strength=1.0 复现旧行为）。
_HEAD_YAW_FACTOR: Final[float] = 0.6
_HEAD_PITCH_FACTOR: Final[float] = 0.18
_HEAD_ROLL_FACTOR: Final[float] = 0.15

_HEAD_FOLLOW_DELAY: Final[float] = 0.12
_HEAD_FOLLOW_DURATION: Final[float] = 0.8
_MIN_SACCADE_DURATION: Final[float] = 0.08
_MAX_SACCADE_DURATION: Final[float] = 0.22
_REACH_MIN_SCALE: Final[float] = 0.4
_MIN_FIXATION: Final[float] = 0.45
_MAX_FIXATION: Final[float] = 1.6
_CENTER_BIAS: Final[float] = 0.2
_CENTER_MICRO_CHANCE: Final[float] = 0.85
_MICRO_GAZE_X_AMPLITUDE: Final[float] = 0.16
_MICRO_GAZE_Y_AMPLITUDE: Final[float] = 0.12
_MIN_MICRO_DURATION: Final[float] = 0.018
_MAX_MICRO_DURATION: Final[float] = 0.045
_MIN_MICRO_FIXATION: Final[float] = 0.015
_MAX_MICRO_FIXATION: Final[float] = 0.025
_BALANCE_WINDOW: Final[int] = 6
_DRIFT_CHANCE: Final[float] = 0.75
_MIN_DRIFT_DURATION: Final[float] = 0.75
_MAX_DRIFT_DURATION: Final[float] = 2.2
_DART_CHANCE: Final[float] = 0.08
_MIN_DART_FIXATION: Final[float] = 0.15
_MAX_DART_FIXATION: Final[float] = 0.5


class GazeController(AnimationController[GazeControllerSettings]):
    """通过眼睛注视语义动作实现待机眼神扰动，并带动头部协调跟随"""

    def __init__(
        self,
        runtime: PlatformAnimationRuntime,
        name: str,
        config: GazeControllerSettings,
    ) -> None:
        super().__init__(runtime, name, config)
        # 记录最近若干次注视方向符号（+1 / -1 / 0 居中），左右、上下各一条，
        # 用于强制两轴均衡，抵消纯随机采样在短时间窗口里偶然偏向一侧的观感。
        window = max(1, _BALANCE_WINDOW)
        self._x_history: deque[int] = deque(maxlen=window)
        self._y_history: deque[int] = deque(maxlen=window)

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次「中心微扰 / 随机注视 + 停留」周期"""

        mode = self._pick_mode()
        gaze_x, gaze_y = self._pick_target(mode)
        style, base_duration, eye_easing, fixation = self._pick_style(mode)

        # 移动幅度（到注视点的归一化距离 0~1）：小幅度看得快，大幅度看得慢。
        # 在风格基准时长上按幅度做线性缩放，下限为基准的 _REACH_MIN_SCALE 倍。
        reach = self._reach_magnitude(gaze_x, gaze_y)
        eye_duration = base_duration * (_REACH_MIN_SCALE + (1.0 - _REACH_MIN_SCALE) * reach)

        head_yaw, head_pitch, head_roll, head_mode = self._head_targets(gaze_x, gaze_y, reach, mode)

        logger.debug(
            "眼神注视[{}:{}]: gaze=({:.2f}, {:.2f}), reach={:.2f}, head=({:.2f}, {:.2f}, {:.2f}){}, 眼动={:.2f}s, 停留={:.2f}s",
            mode,
            style,
            gaze_x,
            gaze_y,
            reach,
            head_yaw,
            head_pitch,
            head_roll,
            f"({head_mode})",
            eye_duration,
            fixation,
        )

        await self.runtime.platform.tween_semantic(
            [
                # 眼睛：按所选风格的时长/缓动移到注视点
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.EYE_GAZE_X,
                    end_value=gaze_x,
                    duration=eye_duration,
                    easing=eye_easing,
                    priority=IDLE_CONTROLLER_PRIORITY,
                ),
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.EYE_GAZE_Y,
                    end_value=gaze_y,
                    duration=eye_duration,
                    easing=eye_easing,
                    priority=IDLE_CONTROLLER_PRIORITY,
                ),
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.HEAD_YAW,
                    end_value=head_yaw,
                    duration=_HEAD_FOLLOW_DURATION,
                    easing=Easing.in_out_sine,
                    delay=_HEAD_FOLLOW_DELAY,
                    priority=IDLE_CONTROLLER_PRIORITY,
                ),
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.HEAD_PITCH,
                    end_value=head_pitch,
                    duration=_HEAD_FOLLOW_DURATION,
                    easing=Easing.in_out_sine,
                    delay=_HEAD_FOLLOW_DELAY,
                    priority=IDLE_CONTROLLER_PRIORITY,
                ),
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.HEAD_ROLL,
                    end_value=head_roll,
                    duration=_HEAD_FOLLOW_DURATION,
                    easing=Easing.in_out_sine,
                    delay=_HEAD_FOLLOW_DELAY,
                    priority=IDLE_CONTROLLER_PRIORITY,
                ),
            ],
        )

        await asyncio.sleep(fixation)

    def _pick_mode(self) -> str:
        return "micro" if random.random() < _CENTER_MICRO_CHANCE else "gaze"

    def _pick_target(self, mode: str) -> tuple[float, float]:
        """选择中心扰动点或随机注视点。

        随机注视仍做方向均衡；中心微扰只在很小范围内高频跳动。
        """

        if mode == "micro":
            gaze_x = random.uniform(-_MICRO_GAZE_X_AMPLITUDE, _MICRO_GAZE_X_AMPLITUDE)
            gaze_y = random.uniform(-_MICRO_GAZE_Y_AMPLITUDE, _MICRO_GAZE_Y_AMPLITUDE)
        else:
            gaze_x = self._balanced_axis(self.config.gaze_x_amplitude, self._x_history)
            gaze_y = self._balanced_axis(self.config.gaze_y_amplitude, self._y_history)
            if random.random() < _CENTER_BIAS:
                gaze_x *= 0.35
                gaze_y *= 0.35
        return gaze_x, gaze_y

    def _balanced_axis(self, amplitude: float, history: deque[int]) -> float:
        """在 [-amplitude, amplitude] 采样一个值，并按历史符号偏差做均衡纠偏。

        history 累计最近若干次的方向符号（+1 偏正 / -1 偏负 / 0 居中）。若历史
        已偏向某侧，则按不平衡比例提高把新采样翻到另一侧的概率；完全均衡时不干预。
        采样后把本次符号记入 history（窗口由 deque maxlen 自动滚动）。
        """

        value = random.uniform(-amplitude, amplitude)
        bias = sum(history)  # >0 说明历史偏正侧，<0 偏负侧
        if bias != 0 and len(history) > 0:
            # 不平衡越严重，翻转概率越高（最高为整窗口一边倒时的 1.0）
            flip_chance = abs(bias) / len(history)
            # 仅当新采样会"加剧"已有偏向时才考虑翻转到另一侧
            if ((bias > 0 and value > 0) or (bias < 0 and value < 0)) and random.random() < flip_chance:
                value = -value
        history.append(1 if value > 0 else -1 if value < 0 else 0)
        return value

    def _reach_magnitude(self, gaze_x: float, gaze_y: float) -> float:
        """到注视点的归一化距离 (0~1)：各轴按自身幅度归一后取欧氏长度并钳位。

        用于把「小幅度看得快、大幅度看得慢」量化：值越大表示这次眼动跨度越大。
        幅度为 0 的轴按 0 处理，避免除零。
        """

        nx = gaze_x / self.config.gaze_x_amplitude if self.config.gaze_x_amplitude > 0 else 0.0
        ny = gaze_y / self.config.gaze_y_amplitude if self.config.gaze_y_amplitude > 0 else 0.0
        return min(1.0, (nx * nx + ny * ny) ** 0.5)

    def _head_targets(self, gaze_x: float, gaze_y: float, reach: float, mode: str) -> tuple[float, float, float, str]:
        if mode == "micro":
            return 0.0, 0.0, 0.0, "不跟随"
        turn_chance = min(1.0, self.config.head_follow_chance + reach * (1.0 - self.config.head_follow_chance))
        if random.random() >= turn_chance:
            return 0.0, 0.0, 0.0, "不跟随"

        follow_sign = -1.0 if random.random() < self.config.reverse_head_chance else 1.0
        mode_name = "反向" if follow_sign < 0 else "跟随"
        strength = self.config.head_follow_strength
        return (
            gaze_x * _HEAD_YAW_FACTOR * strength * follow_sign,
            gaze_y * _HEAD_PITCH_FACTOR * strength * follow_sign,
            gaze_x * _HEAD_ROLL_FACTOR * strength * follow_sign,
            mode_name,
        )

    def _pick_style(self, mode: str) -> tuple[str, float, EasingFunction, float]:
        """随机选一种眼动风格，返回 (名称, 到位时长, 缓动, 凝视时长)

        三种风格按配置概率抽取，其余落到常规扫视：
        - drift 缓慢漂移：长到位 + in_out 缓动，凝视也偏长，像走神/打量。
        - dart 快速连扫：极短到位 + 极短凝视，连续小幅快速瞟动，显得机灵。
        - saccade 常规扫视：默认，快速到位后正常停留。
        """

        if mode == "micro":
            duration = random.uniform(_MIN_MICRO_DURATION, _MAX_MICRO_DURATION)
            fixation = random.uniform(_MIN_MICRO_FIXATION, _MAX_MICRO_FIXATION)
            return "micro", duration, Easing.in_out_sine, fixation

        roll = random.random()
        if roll < _DRIFT_CHANCE:
            duration = random.uniform(_MIN_DRIFT_DURATION, _MAX_DRIFT_DURATION)
            fixation = random.uniform(_MIN_FIXATION, _MAX_FIXATION)
            return "drift", duration, Easing.in_out_sine, fixation
        if roll < _DRIFT_CHANCE + _DART_CHANCE:
            duration = _MIN_SACCADE_DURATION
            fixation = random.uniform(_MIN_DART_FIXATION, _MAX_DART_FIXATION)
            return "dart", duration, Easing.out_cubic, fixation

        duration = random.uniform(_MIN_SACCADE_DURATION, _MAX_SACCADE_DURATION)
        fixation = random.uniform(_MIN_FIXATION, _MAX_FIXATION)
        return "saccade", duration, Easing.out_cubic, fixation

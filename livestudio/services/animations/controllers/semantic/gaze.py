"""各平台都能用的眼神注视控制器

吸收了原 body_swing 的头部摆动职责：单控制器统一驱动 eye.gaze.x/y 与
head.yaw/head.roll，在内部保证「眼睛先到、头部延迟跟随」的时序协调，避免
眼神与头部分属两个独立控制器时争用 head.yaw、反复接管导致的跳变。

一次周期 = 一次眼动 + 一段凝视（fixation）。眼动每次随机选一种风格，避免
节奏单调、显得机械：
- 常规扫视（saccade）：眼睛快速转向新注视点（短时长 + out 缓动）。
- 缓慢漂移（drift）：眼睛慢悠悠移到新点（长时长 + in_out 缓动），像走神/打量。
- 快速连扫（dart）：极短到位 + 极短凝视，连续几次小幅快速瞟动，显得机灵。
头部以较小比例、带延迟、较慢地跟随眼神方向（VOR 式眼头协调）；并按一定概率
反向跟随——眼睛看一侧、头却朝另一侧偏/歪，制造俏皮的歪头与别扭感。

凝视：到位后停在注视点上停留一段随机时长，期间 keep_alive 持续维持参数值，
形成自然的「盯着某处看」效果，而非匀速乱飘。

head.pitch 仍交给 breathing 控制器（点头式呼吸），本控制器不碰，以免冲突。
"""

import asyncio
import random
from collections import deque

from livestudio.services.animations.runtime import PlatformAnimationRuntime
from livestudio.services.semantic_actions import SemanticAction, SemanticTweenRequest
from livestudio.services.tween import Easing, EasingFunction
from livestudio.utils.log import logger

from ..base import AnimationController
from ..config import GazeControllerSettings
from ..models import AnimationType


class GazeController(AnimationController[GazeControllerSettings]):
    """通过眼睛注视语义动作实现待机眼神漫游，并带动头部协调跟随"""

    def __init__(
        self,
        runtime: PlatformAnimationRuntime,
        name: str,
        config: GazeControllerSettings,
    ) -> None:
        super().__init__(runtime, name, config)
        # 记录最近若干次注视方向符号（+1 / -1 / 0 居中），左右、上下各一条，
        # 用于强制两轴均衡，抵消纯随机采样在短时间窗口里偶然偏向一侧的观感。
        window = max(1, config.balance_window)
        self._x_history: deque[int] = deque(maxlen=window)
        self._y_history: deque[int] = deque(maxlen=window)

    @property
    def animation_type(self) -> AnimationType:
        """控制器类型"""

        return AnimationType.IDLE

    async def run_cycle(self) -> None:
        """执行一次「眼动 + 凝视」周期，眼动风格随机选取以避免节奏单调"""

        gaze_x, gaze_y = self._pick_target()

        # 选眼动风格：常规扫视 / 缓慢漂移 / 快速连扫，决定本次到位时长基准与凝视时长
        style, base_duration, eye_easing, fixation = self._pick_style()

        # 移动幅度（到注视点的归一化距离 0~1）：小幅度看得快，大幅度看得慢。
        # 在风格基准时长上按幅度做线性缩放，下限为基准的 reach_min_scale 倍。
        reach = self._reach_magnitude(gaze_x, gaze_y)
        eye_duration = base_duration * (self.config.reach_min_scale + (1.0 - self.config.reach_min_scale) * reach)

        # 头部是否跟随：基础概率 + 幅度加成（看得越偏越可能扭头）。大幅注视几乎必转头，
        # 小幅扫视多为纯眼动、头保持回正，制造「眼动 / 扭头」的层次感。
        turn_chance = min(1.0, self.config.head_follow_chance + reach * (1.0 - self.config.head_follow_chance))
        will_turn = random.random() < turn_chance
        if will_turn:
            # 偶尔反向（看一侧、头朝另一侧）制造俏皮歪头
            follow_sign = -1.0 if random.random() < self.config.reverse_head_chance else 1.0
            head_yaw = gaze_x * self.config.head_follow_ratio * follow_sign
            head_roll = gaze_x * self.config.head_roll_ratio * follow_sign
        else:
            # 不转头：头部回正，眼睛单独动
            follow_sign = 1.0
            head_yaw = 0.0
            head_roll = 0.0

        logger.debug(
            "眼神注视[{}]: gaze=({:.2f}, {:.2f}), reach={:.2f}, head_yaw={:.2f}{}, 眼动={:.2f}s, 凝视={:.2f}s",
            style,
            gaze_x,
            gaze_y,
            reach,
            head_yaw,
            "(反向)" if follow_sign < 0 else "" if will_turn else "(不转头)",
            eye_duration,
            fixation,
        )

        priority = self.config.priority
        await self.runtime.platform.tween_semantic(
            [
                # 眼睛：按所选风格的时长/缓动移到注视点
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.EYE_GAZE_X,
                    end_value=gaze_x,
                    duration=eye_duration,
                    easing=eye_easing,
                    priority=priority,
                ),
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.EYE_GAZE_Y,
                    end_value=gaze_y,
                    duration=eye_duration,
                    easing=eye_easing,
                    priority=priority,
                ),
                # 头部：延迟启动、较慢跟随（VOR 式眼头协调）
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.HEAD_YAW,
                    end_value=head_yaw,
                    duration=self.config.head_follow_duration,
                    easing=Easing.in_out_sine,
                    delay=self.config.head_follow_delay,
                    priority=priority,
                ),
                SemanticTweenRequest(
                    action_parameter_name=SemanticAction.HEAD_ROLL,
                    end_value=head_roll,
                    duration=self.config.head_follow_duration,
                    easing=Easing.in_out_sine,
                    delay=self.config.head_follow_delay,
                    priority=priority,
                ),
            ],
        )

        # 凝视：停在注视点上停留一段时间，期间 keep_alive 维持参数值。
        # 用 sleep 计时即可——新周期或 stop 会取消本任务，无需手动监听 stop_event。
        await asyncio.sleep(fixation)

    def _pick_target(self) -> tuple[float, float]:
        """随机选一个注视点；按 center_bias 概率收缩到中心附近，避免长盯边缘。

        左右、上下两轴各自做方向均衡：纯随机采样在短窗口里可能偶然偏向一侧
        （看右多于看左、或看上多于看下），这里按历史不平衡程度概率翻转新采样
        的符号，使任意时间窗口内两侧分布大致对称。
        """

        gaze_x = self._balanced_axis(self.config.gaze_x_amplitude, self._x_history)
        gaze_y = self._balanced_axis(self.config.gaze_y_amplitude, self._y_history)
        if random.random() < self.config.center_bias:
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

    def _pick_style(self) -> tuple[str, float, EasingFunction, float]:
        """随机选一种眼动风格，返回 (名称, 到位时长, 缓动, 凝视时长)

        三种风格按配置概率抽取，其余落到常规扫视：
        - drift 缓慢漂移：长到位 + in_out 缓动，凝视也偏长，像走神/打量。
        - dart 快速连扫：极短到位 + 极短凝视，连续小幅快速瞟动，显得机灵。
        - saccade 常规扫视：默认，快速到位后正常停留。
        """

        roll = random.random()
        if roll < self.config.drift_chance:
            duration = random.uniform(self.config.min_drift_duration, self.config.max_drift_duration)
            fixation = random.uniform(self.config.min_fixation, self.config.max_fixation)
            return "drift", duration, Easing.in_out_sine, fixation
        if roll < self.config.drift_chance + self.config.dart_chance:
            duration = self.config.min_saccade_duration
            fixation = random.uniform(self.config.min_dart_fixation, self.config.max_dart_fixation)
            return "dart", duration, Easing.out_cubic, fixation

        duration = random.uniform(self.config.min_saccade_duration, self.config.max_saccade_duration)
        fixation = random.uniform(self.config.min_fixation, self.config.max_fixation)
        return "saccade", duration, Easing.out_cubic, fixation

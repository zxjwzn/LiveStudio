"""用于缓动插值的辅助函数"""

import math
from collections.abc import Callable

from livestudio.utils.constants import (
    BACK_C1,
    BACK_C2,
    BACK_C3,
    BOUNCE_D1,
    BOUNCE_N1,
    ELASTIC_C4,
    ELASTIC_C5,
    HALF_PI,
)

EasingFunction = Callable[[float], float]


class Easing:
    @staticmethod
    def linear(t: float) -> float:
        """线性缓动函数，匀速变化"""
        return t

    @staticmethod
    def in_sine(t: float) -> float:
        """正弦缓入函数，缓慢开始加速"""
        return 1 - math.cos(HALF_PI * t)

    @staticmethod
    def out_sine(t: float) -> float:
        """正弦缓出函数，逐渐减速至停止"""
        return math.sin(HALF_PI * t)

    @staticmethod
    def in_out_sine(t: float) -> float:
        """正弦缓入缓出函数，先加速后减速"""
        return 0.5 * (1 + math.sin(math.pi * (t - 0.5)))

    @staticmethod
    def in_quad(t: float) -> float:
        """二次方缓入函数，开始慢后期快"""
        return t * t

    @staticmethod
    def out_quad(t: float) -> float:
        """二次方缓出函数，开始快后期慢"""
        return t * (2 - t)

    @staticmethod
    def in_out_quad(t: float) -> float:
        """二次方缓入缓出函数，先加速后减速"""
        return 2 * t * t if t < 0.5 else t * (4 - 2 * t) - 1

    @staticmethod
    def in_cubic(t: float) -> float:
        """三次方缓入函数，加速度更明显"""
        return t * t * t

    @staticmethod
    def out_cubic(t: float) -> float:
        """三次方缓出函数，减速度更明显"""
        t = t - 1
        return 1 + t * t * t

    @staticmethod
    def in_out_cubic(t: float) -> float:
        """三次方缓入缓出函数，速度变化更剧烈"""
        if t < 0.5:
            return 4 * t * t * t
        t = t - 1
        return 1 + 4 * t * t * t

    @staticmethod
    def in_quart(t: float) -> float:
        """四次方缓入函数，初始加速度非常小"""
        t *= t
        return t * t

    @staticmethod
    def out_quart(t: float) -> float:
        """四次方缓出函数，最终减速度非常大"""
        t -= 1
        t2 = t * t
        return 1 - t2 * t2

    @staticmethod
    def in_out_quart(t: float) -> float:
        """四次方缓入缓出函数，中间过渡更平滑"""
        if t < 0.5:
            t *= t
            return 8 * t * t
        t -= 1
        t2 = t * t
        return 1 - 8 * t2 * t2

    @staticmethod
    def in_quint(t: float) -> float:
        """五次方缓入函数，开始更缓慢"""
        t2 = t * t
        return t * t2 * t2

    @staticmethod
    def out_quint(t: float) -> float:
        """五次方缓出函数，结束更迅速"""
        t -= 1
        t2 = t * t
        return 1 + t * t2 * t2

    @staticmethod
    def in_out_quint(t: float) -> float:
        """五次方缓入缓出函数，中间过渡极其平滑"""
        if t < 0.5:
            t2 = t * t
            return 16 * t * t2 * t2
        t -= 1
        t2 = t * t
        return 1 + 16 * t * t2 * t2

    @staticmethod
    def in_expo(t: float) -> float:
        """指数缓入函数，开始几乎静止（easings.net 标准 2^(10(t-1))）"""
        if t <= 0.0:
            return 0.0
        return pow(2, 10 * (t - 1))

    @staticmethod
    def out_expo(t: float) -> float:
        """指数缓出函数，快速减速到静止（easings.net 标准 1-2^(-10t)）"""
        if t >= 1.0:
            return 1.0
        return 1 - pow(2, -10 * t)

    @staticmethod
    def in_out_expo(t: float) -> float:
        """指数缓入缓出函数，两端极慢中间极快（easings.net 标准）"""
        if t <= 0.0:
            return 0.0
        if t >= 1.0:
            return 1.0
        if t < 0.5:
            return pow(2, 20 * t - 10) / 2
        return (2 - pow(2, -20 * t + 10)) / 2

    @staticmethod
    def in_circ(t: float) -> float:
        """圆形缓入函数，平滑加速"""
        return 1 - math.sqrt(max(0.0, 1 - t * t))

    @staticmethod
    def out_circ(t: float) -> float:
        """圆形缓出函数，平滑减速"""
        t -= 1
        return math.sqrt(max(0.0, 1 - t * t))

    @staticmethod
    def in_out_circ(t: float) -> float:
        """圆形缓入缓出函数，非常平滑的速度变化"""
        if t < 0.5:
            return (1 - math.sqrt(max(0.0, 1 - 4 * t * t))) * 0.5
        t = 2 * t - 2
        return (math.sqrt(max(0.0, 1 - t * t)) + 1) * 0.5

    @staticmethod
    def in_back(t: float) -> float:
        """回退缓入函数，先回退一点再前进（easings.net 标准）"""
        return BACK_C3 * t * t * t - BACK_C1 * t * t

    @staticmethod
    def out_back(t: float) -> float:
        """回退缓出函数，超过终点一点再回退（easings.net 标准）"""
        t -= 1
        return 1 + BACK_C3 * t * t * t + BACK_C1 * t * t

    @staticmethod
    def in_out_back(t: float) -> float:
        """回退缓入缓出函数，两端都有回退效果（easings.net 标准）"""
        if t < 0.5:
            return (pow(2 * t, 2) * ((BACK_C2 + 1) * 2 * t - BACK_C2)) / 2
        return (pow(2 * t - 2, 2) * ((BACK_C2 + 1) * (2 * t - 2) + BACK_C2) + 2) / 2

    @staticmethod
    def in_elastic(t: float) -> float:
        """弹性缓入函数，像橡皮筋一样来回震荡（easings.net 标准）"""
        if t == 0:
            return 0.0
        if t == 1:
            return 1.0
        return -pow(2, 10 * t - 10) * math.sin((t * 10 - 10.75) * ELASTIC_C4)

    @staticmethod
    def out_elastic(t: float) -> float:
        """弹性缓出函数，结束时有弹性震荡效果（easings.net 标准）"""
        if t == 0:
            return 0.0
        if t == 1:
            return 1.0
        return pow(2, -10 * t) * math.sin((t * 10 - 0.75) * ELASTIC_C4) + 1

    @staticmethod
    def in_out_elastic(t: float) -> float:
        """弹性缓入缓出函数，两端都有弹性效果（easings.net 标准）"""
        if t == 0:
            return 0.0
        if t == 1:
            return 1.0
        if t < 0.5:
            return -(pow(2, 20 * t - 10) * math.sin((20 * t - 11.125) * ELASTIC_C5)) / 2
        return (pow(2, -20 * t + 10) * math.sin((20 * t - 11.125) * ELASTIC_C5)) / 2 + 1

    @staticmethod
    def out_bounce(t: float) -> float:
        """弹跳缓出函数，结束时有多次弹跳（easings.net 标准分段实现）"""
        if t < 1 / BOUNCE_D1:
            return BOUNCE_N1 * t * t
        if t < 2 / BOUNCE_D1:
            t -= 1.5 / BOUNCE_D1
            return BOUNCE_N1 * t * t + 0.75
        if t < 2.5 / BOUNCE_D1:
            t -= 2.25 / BOUNCE_D1
            return BOUNCE_N1 * t * t + 0.9375
        t -= 2.625 / BOUNCE_D1
        return BOUNCE_N1 * t * t + 0.984375

    @staticmethod
    def in_bounce(t: float) -> float:
        """弹跳缓入函数，像球落地一样弹跳效果（easings.net 标准：out_bounce 镜像）"""
        return 1 - Easing.out_bounce(1 - t)

    @staticmethod
    def in_out_bounce(t: float) -> float:
        """弹跳缓入缓出函数，两端都有弹跳效果（easings.net 标准）"""
        if t < 0.5:
            return (1 - Easing.out_bounce(1 - 2 * t)) / 2
        return (1 + Easing.out_bounce(2 * t - 1)) / 2


# 自省 Easing 类的全部 staticmethod 自动构建注册表，避免手抄 30+ 行映射、
# 新增缓动函数时漏登记（单一事实源：在 Easing 里加一个 @staticmethod 即自动注册）。
EASING_REGISTRY: dict[str, EasingFunction] = {
    name: member.__func__
    for name, member in vars(Easing).items()
    if isinstance(member, staticmethod)
}

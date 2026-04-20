"""用于缓动插值的辅助函数。"""

from __future__ import annotations

import math
from collections.abc import Callable

EasingFunction = Callable[[float], float]


class Easing:
    @staticmethod
    def linear(t: float) -> float:
        """线性缓动函数，匀速变化"""
        return t

    @staticmethod
    def in_sine(t):
        """正弦缓入函数，缓慢开始加速"""
        return math.sin(1.5707963 * t)

    @staticmethod
    def out_sine(t):
        """正弦缓出函数，逐渐减速至停止"""
        return 1 + math.sin(1.5707963 * (t - 1))

    @staticmethod
    def in_out_sine(t):
        """正弦缓入缓出函数，先加速后减速"""
        return 0.5 * (1 + math.sin(3.1415926 * (t - 0.5)))

    @staticmethod
    def in_quad(t):
        """二次方缓入函数，开始慢后期快"""
        return t * t

    @staticmethod
    def out_quad(t):
        """二次方缓出函数，开始快后期慢"""
        return t * (2 - t)

    @staticmethod
    def in_out_quad(t):
        """二次方缓入缓出函数，先加速后减速"""
        return 2 * t * t if t < 0.5 else t * (4 - 2 * t) - 1

    @staticmethod
    def in_cubic(t):
        """三次方缓入函数，加速度更明显"""
        return t * t * t

    @staticmethod
    def out_cubic(t):
        """三次方缓出函数，减速度更明显"""
        t = t - 1
        return 1 + t * t * t

    @staticmethod
    def in_out_cubic(t):
        """三次方缓入缓出函数，速度变化更剧烈"""
        if t < 0.5:
            return 4 * t * t * t
        t = t - 1
        return 1 + (t) * (2 * (t)) * (2 * t)

    @staticmethod
    def in_quart(t):
        """四次方缓入函数，初始加速度非常小"""
        t *= t
        return t * t

    @staticmethod
    def out_quart(t):
        """四次方缓出函数，最终减速度非常大"""
        t = (t - 1) * t
        return 1 - t * t

    @staticmethod
    def in_out_quart(t):
        """四次方缓入缓出函数，中间过渡更平滑"""
        if t < 0.5:
            t *= t
            return 8 * t * t
        t = (t - 1) * t
        return 1 - 8 * t * t

    @staticmethod
    def in_quint(t):
        """五次方缓入函数，开始更缓慢"""
        t2 = t * t
        return t * t2 * t2

    @staticmethod
    def out_quint(t):
        """五次方缓出函数，结束更迅速"""
        t -= 1
        t2 = t * t
        return 1 + t * t2 * t2

    @staticmethod
    def in_out_quint(t):
        """五次方缓入缓出函数，中间过渡极其平滑"""
        if t < 0.5:
            t2 = t * t
            return 16 * t * t2 * t2
        t -= 1
        t2 = t * t
        return 1 + 16 * t * t2 * t2

    @staticmethod
    def in_expo(t):
        """指数缓入函数，开始几乎静止"""
        return (pow(2, 8 * t) - 1) / 255

    @staticmethod
    def out_expo(t):
        """指数缓出函数，快速减速到静止"""
        return 1 - pow(2, -8 * t)

    @staticmethod
    def in_out_expo(t):
        """指数缓入缓出函数，两端极慢中间极快"""
        if t < 0.5:
            return (pow(2, 16 * t) - 1) / 510
        return 1 - 0.5 * pow(2, -16 * (t - 0.5))

    @staticmethod
    def in_circ(t):
        """圆形缓入函数，平滑加速"""
        return 1 - math.sqrt(1 - t)

    @staticmethod
    def out_circ(t):
        """圆形缓出函数，平滑减速"""
        return math.sqrt(t)

    @staticmethod
    def in_out_circ(t):
        """圆形缓入缓出函数，非常平滑的速度变化"""
        if t < 0.5:
            return (1 - math.sqrt(1 - 2 * t)) * 0.5
        return (1 + math.sqrt(2 * t - 1)) * 0.5

    @staticmethod
    def in_back(t):
        """回退缓入函数，先回退一点再前进"""
        return t * t * (2.70158 * t - 1.70158)

    @staticmethod
    def out_back(t):
        """回退缓出函数，超过终点一点再回退"""
        t -= 1
        return 1 + t * t * (2.70158 * t + 1.70158)

    @staticmethod
    def in_out_back(t):
        """回退缓入缓出函数，两端都有回退效果"""
        if t < 0.5:
            return t * t * (7 * t - 2.5) * 2
        t -= 1
        return 1 + t * t * 2 * (7 * t + 2.5)

    @staticmethod
    def in_elastic(t):
        """弹性缓入函数，像橡皮筋一样来回震荡"""
        t2 = t * t
        return t2 * t2 * math.sin(t * math.pi * 4.5)

    @staticmethod
    def out_elastic(t):
        """弹性缓出函数，结束时有弹性震荡效果"""
        t2 = (t - 1) * (t - 1)
        return 1 - t2 * t2 * math.cos(t * math.pi * 4.5)

    @staticmethod
    def in_out_elastic(t):
        """弹性缓入缓出函数，两端都有弹性效果"""
        if t < 0.45:
            t2 = t * t
            return 8 * t2 * t2 * math.sin(t * math.pi * 9)
        if t < 0.55:
            return 0.5 + 0.75 * math.sin(t * math.pi * 4)
        t2 = (t - 1) * (t - 1)
        return 1 - 8 * t2 * t2 * math.sin(t * math.pi * 9)

    @staticmethod
    def in_bounce(t):
        """弹跳缓入函数，像球落地一样弹跳效果"""
        return pow(2, 6 * (t - 1)) * abs(math.sin(t * math.pi * 3.5))

    @staticmethod
    def out_bounce(t):
        """弹跳缓出函数，结束时有多次弹跳"""
        return 1 - pow(2, -6 * t) * abs(math.cos(t * math.pi * 3.5))

    @staticmethod
    def in_out_bounce(t):
        """弹跳缓入缓出函数，两端都有弹跳效果"""
        if t < 0.5:
            return 8 * pow(2, 8 * (t - 1)) * abs(math.sin(t * math.pi * 7))
        return 1 - 8 * pow(2, -8 * t) * abs(math.sin(t * math.pi * 7))


EASING_REGISTRY: dict[str, EasingFunction] = {
    "linear": Easing.linear,
    "in_sine": Easing.in_sine,
    "out_sine": Easing.out_sine,
    "in_out_sine": Easing.in_out_sine,
    "in_quad": Easing.in_quad,
    "out_quad": Easing.out_quad,
    "in_out_quad": Easing.in_out_quad,
    "in_cubic": Easing.in_cubic,
    "out_cubic": Easing.out_cubic,
    "in_out_cubic": Easing.in_out_cubic,
    "in_quart": Easing.in_quart,
    "out_quart": Easing.out_quart,
    "in_out_quart": Easing.in_out_quart,
    "in_quint": Easing.in_quint,
    "out_quint": Easing.out_quint,
    "in_out_quint": Easing.in_out_quint,
    "in_expo": Easing.in_expo,
    "out_expo": Easing.out_expo,
    "in_out_expo": Easing.in_out_expo,
    "in_circ": Easing.in_circ,
    "out_circ": Easing.out_circ,
    "in_out_circ": Easing.in_out_circ,
    "in_back": Easing.in_back,
    "out_back": Easing.out_back,
    "in_out_back": Easing.in_out_back,
    "in_elastic": Easing.in_elastic,
    "out_elastic": Easing.out_elastic,
    "in_out_elastic": Easing.in_out_elastic,
    "in_bounce": Easing.in_bounce,
    "out_bounce": Easing.out_bounce,
    "in_out_bounce": Easing.in_out_bounce,
}

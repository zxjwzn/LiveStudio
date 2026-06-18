"""测试缓动函数注册表与边界值

覆盖：
- EASING_REGISTRY 包含所有 Easing 类方法
- 所有缓动函数 f(0)≈0, f(1)≈1
- 线性缓动 f(0.5)=0.5
- 注册表名与 Easing 类方法名一致
"""

from __future__ import annotations

import pytest

from livestudio.utils.easing import EASING_REGISTRY, Easing


def _all_easing_names() -> list[str]:
    """收集 Easing 类上所有公开静态方法名"""
    return [name for name in dir(Easing) if not name.startswith("_") and callable(getattr(Easing, name))]


def test_registry_contains_all_easing_class_methods() -> None:
    method_names = set(_all_easing_names())
    registry_names = set(EASING_REGISTRY.keys())
    assert (
        method_names == registry_names
    ), f"注册表与 Easing 类方法不一致: 缺少 {method_names - registry_names}, 多余 {registry_names - method_names}"


def test_registry_values_match_class_methods() -> None:
    for name in _all_easing_names():
        assert EASING_REGISTRY[name] is getattr(Easing, name), f"注册表 {name} 指向的函数与 Easing.{name} 不一致"


@pytest.mark.parametrize("name", list(EASING_REGISTRY.keys()))
def test_easing_at_zero(name: str) -> None:
    fn = EASING_REGISTRY[name]
    assert fn(0.0) == pytest.approx(0.0, abs=0.01), f"Easing.{name}(0) 应接近 0"


def test_out_quart_at_midpoint() -> None:
    # 四次方缓出 f(0.5) = 1 - (0.5-1)^4 = 1 - 0.0625 = 0.9375
    assert Easing.out_quart(0.5) == pytest.approx(0.9375)


@pytest.mark.parametrize("name", list(EASING_REGISTRY.keys()))
def test_easing_at_one(name: str) -> None:
    fn = EASING_REGISTRY[name]
    assert fn(1.0) == pytest.approx(1.0, abs=0.01), f"Easing.{name}(1) 应接近 1"


def test_linear_at_midpoint() -> None:
    assert Easing.linear(0.5) == pytest.approx(0.5)


def test_in_quad_at_midpoint() -> None:
    assert Easing.in_quad(0.5) == pytest.approx(0.25)


def test_out_quad_at_midpoint() -> None:
    assert Easing.out_quad(0.5) == pytest.approx(0.75)


@pytest.mark.parametrize("name", list(EASING_REGISTRY.keys()))
def test_easing_returns_float(name: str) -> None:
    fn = EASING_REGISTRY[name]
    result = fn(0.5)
    assert isinstance(result, (int, float)), f"Easing.{name}(0.5) 应返回数值类型，实际返回 {type(result)}"

"""动画模板加载与求值。"""

from __future__ import annotations

import ast
import random
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import json5

from livestudio.log import logger

from .models import (
    TEMPLATE_PRIORITY,
    AnimationTemplate,
    ResolvedTemplateAction,
    TemplateActionDefinition,
    TemplatePlayback,
    TemplateScalar,
    TemplateValue,
)


class TemplateEvaluationError(ValueError):
    """模板求值失败。"""


class SafeExpressionEvaluator(ast.NodeVisitor):
    """受限表达式求值器。"""

    _binary_operators: dict[type[ast.operator], Any] = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a**b,
    }
    _unary_operators: dict[type[ast.unaryop], Any] = {
        ast.UAdd: lambda a: +a,
        ast.USub: lambda a: -a,
    }
    _allowed_functions: dict[str, Any] = {
        "min": min,
        "max": max,
        "abs": abs,
        "round": round,
        "int": int,
        "float": float,
    }

    def __init__(self, context: Mapping[str, TemplateScalar]) -> None:
        self._context = context

    def evaluate(self, expression: str) -> TemplateScalar:
        tree = ast.parse(expression, mode="eval")
        return self.visit(tree.body)

    def visit_Constant(self, node: ast.Constant) -> TemplateScalar:  # noqa: N802
        value = node.value
        if isinstance(value, (int, float, bool, str)):
            return value
        raise TemplateEvaluationError(f"不支持的常量类型: {type(value)!r}")

    def visit_Name(self, node: ast.Name) -> TemplateScalar:  # noqa: N802
        if node.id not in self._context:
            raise TemplateEvaluationError(f"表达式引用了未定义变量: {node.id}")
        return self._context[node.id]

    def visit_BinOp(self, node: ast.BinOp) -> TemplateScalar:  # noqa: N802
        operator = self._binary_operators.get(type(node.op))
        if operator is None:
            raise TemplateEvaluationError(f"不支持的二元运算: {type(node.op).__name__}")
        return operator(self.visit(node.left), self.visit(node.right))

    def visit_UnaryOp(self, node: ast.UnaryOp) -> TemplateScalar:  # noqa: N802
        operator = self._unary_operators.get(type(node.op))
        if operator is None:
            raise TemplateEvaluationError(f"不支持的一元运算: {type(node.op).__name__}")
        return operator(self.visit(node.operand))

    def visit_Call(self, node: ast.Call) -> TemplateScalar:  # noqa: N802
        if not isinstance(node.func, ast.Name):
            raise TemplateEvaluationError("仅支持调用白名单函数")
        function = self._allowed_functions.get(node.func.id)
        if function is None:
            raise TemplateEvaluationError(f"不支持的函数调用: {node.func.id}")
        if node.keywords:
            raise TemplateEvaluationError("表达式暂不支持关键字参数")
        return function(*(self.visit(argument) for argument in node.args))

    def visit_List(self, node: ast.List) -> TemplateScalar:  # noqa: N802
        _ = node
        raise TemplateEvaluationError("表达式中不支持列表字面量")

    def visit_Tuple(self, node: ast.Tuple) -> TemplateScalar:  # noqa: N802
        _ = node
        raise TemplateEvaluationError("表达式中不支持元组字面量")

    def generic_visit(self, node: ast.AST) -> TemplateScalar:
        raise TemplateEvaluationError(f"表达式包含不支持的语法: {type(node).__name__}")


class AnimationTemplateRepository:
    """动画模板仓库。"""

    def __init__(self, template_dir: Path) -> None:
        self._template_dir = template_dir
        self._templates: dict[str, AnimationTemplate] = {}

    @property
    def template_dir(self) -> Path:
        return self._template_dir

    @property
    def templates(self) -> dict[str, AnimationTemplate]:
        return dict(self._templates)

    async def load(self) -> None:
        self._templates.clear()
        if not self._template_dir.exists():
            logger.warning("动画模板目录不存在，已跳过加载: {}", self._template_dir)
            return

        for path in sorted(self._template_dir.glob("*.jsonc")):
            template = AnimationTemplate.model_validate(json5.loads(path.read_text(encoding="utf-8")))
            if template.name in self._templates:
                raise ValueError(f"重复的动画模板名称: {template.name}")
            self._templates[template.name] = template

        logger.info("已加载 {} 个动画模板", len(self._templates))

    def get(self, name: str) -> AnimationTemplate:
        template = self._templates.get(name)
        if template is None:
            raise KeyError(f"未知动画模板: {name}")
        return template

    def render(
        self,
        name: str,
        *,
        parameters: Mapping[str, TemplateScalar] | None = None,
    ) -> TemplatePlayback:
        template = self.get(name)
        context = self._prepare_context(template, parameters or {})
        actions = [
            self._resolve_action(
                action,
                context=context,
            )
            for action in template.data.actions
        ]
        return TemplatePlayback(template_name=template.name, context=context, actions=actions)

    def _prepare_context(
        self,
        template: AnimationTemplate,
        parameters: Mapping[str, TemplateScalar],
    ) -> dict[str, TemplateScalar]:
        context: dict[str, TemplateScalar] = {}
        for definition in template.data.params:
            if definition.name in parameters:
                context[definition.name] = parameters[definition.name]
                continue
            if definition.default is not None:
                context[definition.name] = definition.default
                continue
            if definition.required:
                raise TemplateEvaluationError(f"模板参数缺失: {definition.name}")
            raise TemplateEvaluationError(f"模板参数未提供默认值: {definition.name}")

        for variable_name, raw_value in template.data.variables.items():
            context[variable_name] = self._evaluate_value(raw_value, context)

        return context

    def _resolve_action(
        self,
        action: TemplateActionDefinition,
        *,
        context: Mapping[str, TemplateScalar],
    ) -> ResolvedTemplateAction:
        from_value = None if action.from_value is None else float(self._evaluate_value(action.from_value, context))
        return ResolvedTemplateAction(
            parameter=action.parameter,
            to=float(self._evaluate_value(action.to, context)),
            duration=float(self._evaluate_value(action.duration, context)),
            from_value=from_value,
            delay=float(self._evaluate_value(action.delay, context)),
            easing=action.easing,
            mode=action.mode,
            priority=TEMPLATE_PRIORITY,
            keep_alive=True,
        )

    def _evaluate_value(
        self,
        raw_value: TemplateValue,
        context: Mapping[str, TemplateScalar],
    ) -> TemplateScalar:
        if isinstance(raw_value, (int, float, bool, str)):
            return raw_value
        if not isinstance(raw_value, dict):
            raise TemplateEvaluationError(f"不支持的模板值类型: {type(raw_value)!r}")

        if "expr" in raw_value:
            expr = raw_value["expr"]
            if not isinstance(expr, str):
                raise TemplateEvaluationError("expr 必须是字符串")
            evaluator = SafeExpressionEvaluator(context)
            return evaluator.evaluate(expr)

        if "random_float" in raw_value:
            random_value = raw_value["random_float"]
            if not isinstance(random_value, (list, tuple)) or len(random_value) != 2:
                raise TemplateEvaluationError("random_float 必须是长度为 2 的数组")
            start, end = random_value
            return random.uniform(float(start), float(end))

        if "random_int" in raw_value:
            random_value = raw_value["random_int"]
            if not isinstance(random_value, (list, tuple)) or len(random_value) != 2:
                raise TemplateEvaluationError("random_int 必须是长度为 2 的数组")
            start, end = random_value
            return random.randint(int(start), int(end))

        raise TemplateEvaluationError(f"未知模板值声明: {raw_value}")

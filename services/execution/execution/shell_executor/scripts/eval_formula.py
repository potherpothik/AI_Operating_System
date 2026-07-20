#!/usr/bin/env python3
"""
Phase 17: real, deterministic formula evaluation for Calculation Agent —
never the model's own arithmetic. A restricted ast walker: only numeric
literals, named variables (resolved against the supplied inputs), binary
arithmetic, and unary +/- are permitted. No calls, no attribute access,
no imports, no comprehensions — structurally incapable of executing
anything beyond arithmetic, regardless of what expression string reaches
it (never Python's own eval(), which would execute arbitrary code).

Usage: eval_formula.py <expression> <inputs_json>
Prints {"result": <number>} on success, {"error": "..."} with exit 1 on failure.
"""
import ast
import json
import operator
import sys

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class DisallowedExpression(Exception):
    pass


def _eval_node(node, inputs: dict):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, inputs)
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise DisallowedExpression(f"non-numeric constant: {node.value!r}")
        return node.value
    if isinstance(node, ast.Name):
        if node.id not in inputs:
            raise DisallowedExpression(f"unresolved variable: {node.id!r}")
        value = inputs[node.id]
        if not isinstance(value, (int, float)):
            raise DisallowedExpression(f"input {node.id!r} is not numeric: {value!r}")
        return value
    if isinstance(node, ast.BinOp):
        op = _ALLOWED_BINOPS.get(type(node.op))
        if op is None:
            raise DisallowedExpression(f"disallowed binary operator: {type(node.op).__name__}")
        return op(_eval_node(node.left, inputs), _eval_node(node.right, inputs))
    if isinstance(node, ast.UnaryOp):
        op = _ALLOWED_UNARYOPS.get(type(node.op))
        if op is None:
            raise DisallowedExpression(f"disallowed unary operator: {type(node.op).__name__}")
        return op(_eval_node(node.operand, inputs))
    raise DisallowedExpression(f"disallowed expression element: {type(node).__name__}")


def evaluate(expression: str, inputs: dict):
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise DisallowedExpression(f"not a valid arithmetic expression: {e}")
    return _eval_node(tree, inputs)


def main():
    if len(sys.argv) != 3:
        print(json.dumps({"error": "usage: eval_formula.py <expression> <inputs_json>"}))
        sys.exit(1)
    expression, inputs_raw = sys.argv[1], sys.argv[2]
    try:
        inputs = json.loads(inputs_raw)
        if not isinstance(inputs, dict):
            raise ValueError("inputs_json must be a JSON object")
    except (json.JSONDecodeError, ValueError) as e:
        print(json.dumps({"error": f"invalid inputs_json: {e}"}))
        sys.exit(1)

    try:
        result = evaluate(expression, inputs)
    except DisallowedExpression as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    except ZeroDivisionError:
        print(json.dumps({"error": "division by zero"}))
        sys.exit(1)

    print(json.dumps({"result": result}))


if __name__ == "__main__":
    main()

import ast
from pathlib import Path


def _signature(node) -> str:
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({args}){returns}"


def _calls_within(node) -> list[str]:
    """
    Names this symbol's body calls — resolved against other symbols in
    the SAME file by symbol_extractor.py/call_graph.py. Cross-file calls
    aren't tracked in this first version (see models.py's CallEdge
    docstring); a call through an attribute (`self.x()`, `obj.method()`)
    records just the trailing name, the same coarse resolution the
    intra-file-only scope already accepts.
    """
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                calls.append(func.id)
            elif isinstance(func, ast.Attribute):
                calls.append(func.attr)
    return calls


def _function_symbol(node, qualified_prefix: str) -> dict:
    qualified_name = f"{qualified_prefix}.{node.name}" if qualified_prefix else node.name
    return {
        "symbol_type": "function",
        "name": node.name,
        "qualified_name": qualified_name,
        "signature": _signature(node),
        "docstring": ast.get_docstring(node),
        "line_number": node.lineno,
        "calls": _calls_within(node),
    }


def _class_symbol(node) -> dict:
    bases = [ast.unparse(b) for b in node.bases]
    signature = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
    return {
        "symbol_type": "class",
        "name": node.name,
        "qualified_name": node.name,
        "signature": signature,
        "docstring": ast.get_docstring(node),
        "line_number": node.lineno,
        "calls": [],
    }


def parse(path: str) -> dict:
    """
    Real static analysis via Python's own `ast` module — no external
    dependency, no regex approximation. Extracts module/class/function
    docstrings and signatures (the structural tier) plus a same-file
    call reference list per symbol, which call_graph.py resolves into
    CallEdge rows. Function/method BODIES are deliberately never
    returned here — raw_source_gate.py reads those live from disk on an
    approved request instead (Phase 11 doc's two-tier split).
    """
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=path)

    # ast.walk() doesn't track parent nodes, so class methods (handled
    # via their enclosing ClassDef, to get the right qualified_name
    # prefix) and module-level functions need separate, explicit passes
    # rather than one flat walk that can't tell nesting apart.
    symbols = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append(_class_symbol(node))
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols.append(_function_symbol(child, node.name))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(_function_symbol(node, ""))

    return {
        "module_docstring": ast.get_docstring(tree),
        "symbols": symbols,
    }

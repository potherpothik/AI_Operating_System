"""
Phase 28 — the real enforcement half of "agents may not make bespoke
third-party calls" (docs/contracts/README.md). A static AST scan, not a
runtime interceptor — Security Layer has no way to observe a Python
function call before it happens, so the actual gate here is "this test
fails the build if a new module imports httpx/requests directly outside
the small, fixed set of registered adapter modules." Every module this
test scans is real, on-disk source under services/agents/agents/ — not a
sample or a subset.
"""
import ast
from pathlib import Path

AGENTS_ROOT = Path(__file__).parent.parent / "agents"

# The only modules allowed to import an HTTP client directly — every
# other module under services/agents/agents/ must reach a network
# destination exclusively through agents/clients.py's own wrapper
# functions (which is itself one of these three). Adding a new adapter
# module here should be a deliberate, reviewed decision, same as adding
# a new registered MCP server or a new Shell Executor allowlist entry.
ALLOWED_DIRECT_HTTP_MODULES = {
    AGENTS_ROOT / "clients.py",
    AGENTS_ROOT / "reasoning_engine" / "model_router.py",
    AGENTS_ROOT / "reasoning_engine" / "ollama_adapter.py",
}

_HTTP_CLIENT_MODULES = {"httpx", "requests", "urllib.request", "http.client"}


def _imports_http_client_directly(path: Path) -> bool:
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name in _HTTP_CLIENT_MODULES for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module in _HTTP_CLIENT_MODULES:
                return True
    return False


def test_no_bespoke_http_clients_outside_registered_adapter_modules():
    violations = [
        str(path.relative_to(AGENTS_ROOT.parent))
        for path in AGENTS_ROOT.rglob("*.py")
        if path not in ALLOWED_DIRECT_HTTP_MODULES and _imports_http_client_directly(path)
    ]
    assert not violations, (
        "the following modules import an HTTP client directly instead of going "
        f"through agents/clients.py (the registered adapter): {violations}"
    )


def test_allowed_adapter_modules_still_exist():
    """A guard against the allowlist silently going stale — if one of
    these files gets renamed or removed, this test should fail loudly
    rather than the boundary check above just quietly scanning fewer
    files than intended."""
    missing = [str(p) for p in ALLOWED_DIRECT_HTTP_MODULES if not p.exists()]
    assert not missing, f"allowlisted adapter module(s) no longer exist: {missing}"

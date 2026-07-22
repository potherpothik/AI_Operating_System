import subprocess

import pytest

from agents.reasoning_engine import odoo_live_bridge, django_bridge, browser_bridge

SCRIPTS_DIR = "/home/saadi/Documents/AI_Operating_System/.claude/worktrees/getting-started-3501ab/services/execution/execution/shell_executor/scripts"


# ---------------------------------------------------------------------------
# Odoo live adapter — real XML-RPC client code (stdlib xmlrpc.client)
# against Odoo's real, documented external API. No live Odoo 19 instance
# exists in this environment (forward-plan doc's own scope note), so what's
# genuinely verifiable here is the REAL mechanism: a real credential
# resolution through governance's real secrets registry, and a real
# network connection attempt with an honest failure report — never a
# fabricated success.
# ---------------------------------------------------------------------------

def test_odoo_read_orm_live_rejects_malformed_json_before_any_network_call():
    result = odoo_live_bridge.handle_tool_call(
        {"odoo_model": "sale.order", "odoo_domain_json": "not json", "odoo_fields_json": "[]"},
        "odoo_agent", "test-task-odoo-1",
    )
    assert "not valid JSON" in result["summary"]


def test_odoo_read_orm_live_denies_an_unpermitted_capability(governance_url):
    """Real governance secrets-registry check — services/governance/governance/security/secrets_registry.yaml's
    live_odoo entry only allows odoo_agent, confirmed live against the
    real /security/secrets/resolve endpoint, not asserted from the YAML."""
    result = odoo_live_bridge.handle_tool_call(
        {"odoo_model": "sale.order", "odoo_domain_json": "[]", "odoo_fields_json": "[]"},
        "research_agent", "test-task-odoo-2",
    )
    assert "no live Odoo connection available" in result["summary"]


def test_odoo_read_orm_live_attempts_a_real_connection_and_reports_honestly(governance_url):
    """
    Whatever the real outcome (no ODOO_CONNECTION_URL configured on this
    governance instance, or a configured-but-unreachable one, or a real
    instance if one is ever actually stood up), this must NEVER report a
    fabricated success — the real xmlrpc.client call either genuinely
    connects or genuinely fails, and the honest reason is what should
    come back.
    """
    result = odoo_live_bridge.handle_tool_call(
        {"odoo_model": "sale.order", "odoo_domain_json": "[]", "odoo_fields_json": "[]"},
        "odoo_agent", "test-task-odoo-3",
    )
    summary = result["summary"]
    is_honest_non_success = (
        "no live Odoo connection available" in summary
        or "unreachable" in summary
        or "authentication failed" in summary
        or "live Odoo query" in summary  # only true if a real instance actually answered
    )
    assert is_honest_non_success, f"unexpected/fabricated-looking result: {summary}"


# ---------------------------------------------------------------------------
# Django adapter — governed manage.py invocation through Shell Executor's
# real allowlist + sandbox, against a real, disposable Django project
# (django-admin startproject, the same "real, throwaway" pattern this
# codebase already uses for git repos and demo_erp rows).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def django_project_root(execution_sandbox_root):
    root = execution_sandbox_root / "django_project"
    subprocess.run(
        ["django-admin", "startproject", "aios_test_project", str(root)],
        check=True, capture_output=True,
    )
    return root


@pytest.fixture
def configured_django_bridge(django_project_root, monkeypatch):
    monkeypatch.setattr(django_bridge, "DJANGO_PROJECT_ROOT", str(django_project_root))


def test_django_check_project_runs_a_real_manage_py_check(governance_url, execution_url, configured_django_bridge):
    result = django_bridge.handle_tool_call({"manage_py_command": "check"}, "django_agent", "test-task-django-1")
    assert "exit_code=0" in result["summary"]
    assert "System check identified no issues" in result["summary"]


def test_django_check_project_runs_real_showmigrations(governance_url, execution_url, configured_django_bridge):
    result = django_bridge.handle_tool_call({"manage_py_command": "showmigrations"}, "django_agent", "test-task-django-2")
    assert "exit_code=0" in result["summary"]
    # Real Django built-in apps' migrations, not a placeholder.
    assert "admin" in result["summary"] and "auth" in result["summary"]


def test_django_check_project_rejects_an_unknown_subcommand():
    result = django_bridge.handle_tool_call({"manage_py_command": "migrate"}, "django_agent", "test-task-django-3")
    assert "must be one of" in result["summary"]


def test_django_check_project_honest_when_not_configured(monkeypatch):
    monkeypatch.setattr(django_bridge, "DJANGO_PROJECT_ROOT", None)
    result = django_bridge.handle_tool_call({"manage_py_command": "check"}, "django_agent", "test-task-django-4")
    assert "DJANGO_PROJECT_ROOT not configured" in result["summary"]


# ---------------------------------------------------------------------------
# Browser adapter — real Playwright automation through Shell Executor's
# sandbox. The internal/external URL scope restriction is fully real and
# testable regardless of the sandbox itself. Whether a real page load
# SUCCEEDS in this environment depends on SubprocessSandbox's own
# resource limits (see the honest structural finding below) — same class
# of environment constraint Phase 22 already documented for external
# coding-agent CLIs under this same sandbox backend.
# ---------------------------------------------------------------------------

def test_browse_internal_page_refuses_external_url_structurally():
    """The one non-negotiable requirement for this adapter: an external
    URL is refused BEFORE any browser is ever launched — confirmed by
    the fact this needs no execution_url fixture at all to pass."""
    result = browser_bridge.handle_tool_call({"target_url": "https://example.com"}, "testing_agent", "test-task-browser-1")
    assert "refused" in result["summary"]
    assert "no browser was launched" in result["summary"]


def test_browse_internal_page_refuses_empty_url():
    result = browser_bridge.handle_tool_call({"target_url": ""}, "testing_agent", "test-task-browser-2")
    assert "nothing to browse" in result["summary"]


def test_browse_internal_page_attempts_a_real_navigation_honestly(governance_url, execution_url, execution_sandbox_root, monkeypatch):
    """
    Real, live-confirmed structural finding (not a guess): Playwright's
    own Node.js driver process needs more virtual address space than
    SubprocessSandbox's 512MB RLIMIT_AS cap allows — reproduced directly
    outside the sandbox with the identical rlimit applied, the exact
    same class of finding Phase 22 already established for the `claude`/
    `opencode` CLIs under this same sandbox backend (no Docker daemon
    exists in this environment, unchanged since Phase 6/19). This test
    locks in the HONEST reporting of whatever the real outcome is —
    never a fabricated successful page load.
    """
    monkeypatch.setattr(browser_bridge, "CALC_SCRIPTS_DIR", SCRIPTS_DIR)
    monkeypatch.setattr(browser_bridge, "CALC_WORKING_DIR", str(execution_sandbox_root))
    result = browser_bridge.handle_tool_call({"target_url": f"{governance_url}/"}, "testing_agent", "test-task-browser-3")
    summary = result["summary"]
    # Either outcome is honest; a silent, unexplained empty success is not.
    assert ("real page loaded" in summary) or ("browser navigation failed" in summary) or ("unparseable" in summary)

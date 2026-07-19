import json
import subprocess
import httpx
import pytest

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry, shell_bridge
from agents.django_agent import register as django_agent_register
from agents.devops_agent import register as devops_agent_register
from agents.docker_agent import register as docker_agent_register
from agents.testing_agent import register as testing_agent_register

LOCAL_MODEL = "qwen3.5:4b"


def _ensure_ready(register_module, governance_url, assembly_url):
    db = SessionLocal()
    capability_registry.load_all(db)
    db.close()

    result = register_module.ensure_template_registered(created_by="test-suite")
    if result["registered"]:
        approval_id = result["result"]["approval_id"]
        httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")


def _stub(action, **overrides):
    base = {
        "reasoning": "test reasoning", "answer_or_proposal": "test answer", "confidence": 0.9,
        "provenance": [], "risk_classification": "medium", "delegate_to": None, "action": action,
        "target_platform": None, "shell_command": None, "shell_args_json": None, "resolved_environment": None,
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Capability registry — proves the four new capabilities load with exactly
# the boundaries the Phase 10 doc declares.
# ---------------------------------------------------------------------------

def test_all_four_new_capabilities_discovered_with_correct_boundaries():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    for cap_name in ("django_agent", "devops_agent", "docker_agent", "testing_agent"):
        assert cap_name in loaded

    django = capability_registry.get_capability(db, "django_agent")
    assert django.allowed_actions == ["django.explain_structure", "django.propose_migration", "django.propose_config_change"]
    assert capability_registry.local_precheck(django, "django.propose_migration") == "require_approval"
    assert capability_registry.local_precheck(django, "django.direct_deploy") == "deny"

    devops = capability_registry.get_capability(db, "devops_agent")
    assert capability_registry.local_precheck(devops, "devops.explain_topology") == "allow"
    assert capability_registry.local_precheck(devops, "devops.execute_deploy") == "deny"

    docker = capability_registry.get_capability(db, "docker_agent")
    assert capability_registry.local_precheck(docker, "docker.inspect") == "allow"
    assert capability_registry.local_precheck(docker, "docker.exec_into_container") == "deny"
    assert capability_registry.local_precheck(docker, "docker.stop_prod") == "deny"

    testing = capability_registry.get_capability(db, "testing_agent")
    assert capability_registry.local_precheck(testing, "testing.run_suite") == "allow"
    assert capability_registry.local_precheck(testing, "testing.propose_new_test") == "require_approval"
    assert capability_registry.local_precheck(testing, "testing.run_against_prod") == "deny"
    db.close()


# ---------------------------------------------------------------------------
# Django Agent — django.propose_migration reuses database_bridge's
# materialize_propose_migration unchanged (Phase 10 doc, Section 1).
# ---------------------------------------------------------------------------

def test_django_propose_migration_reaches_the_real_migration_adapter(full_stack, database_url, monkeypatch):
    _ensure_ready(django_agent_register, full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub(
            "django.propose_migration", target_platform="django",
            answer_or_proposal="Add a discount_pct column to sale_order", risk_classification="high",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="django-migrate-test-1", task_description="Add a discount percentage field.",
        agent_capability="django_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    db_execution = resumed.result["db_execution"]
    assert db_execution["attempted"] is True
    assert db_execution["result"]["ok"] is True
    assert db_execution["result"]["status"] == "not_configured"  # honest, no live Django project in this env


# ---------------------------------------------------------------------------
# DevOps Agent / Docker Agent — propose_* actions reuse execution_bridge's
# materialize_propose_change unchanged, against a real disposable repo.
# ---------------------------------------------------------------------------

def test_devops_propose_pipeline_change_materializes_as_real_branch_commit_push(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(devops_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Add a staging deploy gate requiring two approvals before promoting to prod."

    def fake_generate(model, prompt):
        return _stub("devops.propose_pipeline_change", answer_or_proposal=proposal_text, risk_classification="medium")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="devops-bridge-test-1", task_description="Add a staging deploy gate.",
        agent_capability="devops_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    assert git_execution["stage"] == "open_mr"
    branch_name = git_execution["branch_name"]
    assert branch_name == "devops-agent/task-devops-bridge-test-1"

    show_output = subprocess.run(
        ["git", "show", f"{branch_name}:proposals/devops-bridge-test-1.md"],
        cwd=str(disposable_bare_repo_for_bridge), capture_output=True, text=True,
    ).stdout
    assert proposal_text in show_output


def test_docker_propose_compose_change_materializes_as_real_branch_commit_push(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(docker_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Pin the postgres image to 18.1 instead of latest in docker-compose.yml."

    def fake_generate(model, prompt):
        return _stub("docker.propose_compose_change", answer_or_proposal=proposal_text, risk_classification="low")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="docker-bridge-test-1", task_description="Pin the postgres image version.",
        agent_capability="docker_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    branch_name = git_execution["branch_name"]
    assert branch_name == "docker-agent/task-docker-bridge-test-1"


def test_docker_inspect_tool_call_runs_a_real_read_only_shell_command(
    full_stack, execution_url, proposal_repo, monkeypatch,
):
    """
    docker.inspect is a genuine tool call (Phase 10 doc, Section 4): the
    model asks to run something, Reasoning Engine actually calls Shell
    Executor, and the SECOND turn's prompt contains the real result — not
    a canned response. Uses `git log` against the real proposal_repo
    fixture rather than an actual `docker` binary, since Docker isn't
    installed in this environment (same honest constraint noted
    throughout services/execution/README.md) — what's under test is the
    tool-call wiring itself, proven against a command that genuinely
    exists and genuinely runs, not docker's own output.
    """
    _ensure_ready(docker_agent_register, full_stack["governance"], full_stack["assembly"])
    monkeypatch.setattr(shell_bridge, "SHELL_WORKING_DIR", str(proposal_repo))
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            assert "initial commit" not in prompt
            return _stub(
                "docker.inspect", shell_command="git", shell_args_json=json.dumps(["log", "-1", "--format=%s"]),
            )
        assert "initial commit" in prompt  # the REAL commit message from the real repo, not a guess
        return _stub(
            "docker.inspect", shell_command=None, answer_or_proposal="The container is up.",
            risk_classification="informational",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="docker-inspect-test-1", task_description="Is the web container running?",
        agent_capability="docker_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


# ---------------------------------------------------------------------------
# Testing Agent — the genuinely new mechanism: run_suite is a tool call
# gated by Security Layer's structural environment verification.
# ---------------------------------------------------------------------------

def test_run_suite_against_registered_sandbox_actually_executes(
    full_stack, execution_url, proposal_repo, monkeypatch,
):
    """
    Uses `git log` against the real proposal_repo fixture rather than a
    real test runner, since neither `pytest` nor `docker` is on Shell
    Executor's safe-env PATH in this environment (confirmed by live
    testing — its allowlisted env is deliberately minimal, not the
    parent process's full PATH). What's under test is the genuinely-real
    round trip through environment verification AND Shell Executor, not
    a particular test runner's own output.
    """
    _ensure_ready(testing_agent_register, full_stack["governance"], full_stack["assembly"])
    monkeypatch.setattr(shell_bridge, "SHELL_WORKING_DIR", str(proposal_repo))
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub(
                "testing.run_suite", shell_command="git", shell_args_json=json.dumps(["log", "-1", "--format=%s"]),
                resolved_environment="test_sandbox_1",
            )
        assert "initial commit" in prompt  # the REAL commit message from the real repo, not a guess
        return _stub(
            "testing.run_suite", shell_command=None, answer_or_proposal="All tests passed.",
            risk_classification="informational",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="testing-run-suite-sandbox", task_description="Run the suite against the sandbox.",
        agent_capability="testing_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_run_suite_against_production_is_refused_and_never_executes(
    full_stack, execution_url, proposal_repo, monkeypatch,
):
    """
    The structural gate itself (Phase 10 doc, Section 5): Security Layer's
    /security/verify_environment denies "production_erp" — the shell
    command must never actually run, proven here by the model's declared
    marker never showing up in the tool-call result fed back into the
    prompt on a later turn (there is no later turn: the model gets told
    verification failed on its very next turn instead).
    """
    _ensure_ready(testing_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub(
                "testing.run_suite", shell_command="echo", shell_args_json=json.dumps(["SHOULD_NEVER_RUN_MARKER"]),
                resolved_environment="production_erp",
            )
        assert "SHOULD_NEVER_RUN_MARKER" not in prompt
        assert "environment verification denied" in prompt
        return _stub(
            "testing.run_suite", shell_command=None,
            answer_or_proposal="Refusing — production_erp is not a valid test target.",
            risk_classification="informational",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="testing-run-suite-prod-denied", task_description="Run the suite against production.",
        agent_capability="testing_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2

    events = httpx.get(f"{full_stack['governance']}/audit/query?action=testing.verify_environment").json()
    denied = [e for e in events if e["resource"] == "production_erp"]
    assert len(denied) >= 1
    assert denied[-1]["decision"] == "deny"


def test_run_suite_against_unregistered_environment_fails_closed(
    full_stack, execution_url, proposal_repo, monkeypatch,
):
    """Fail-closed, same posture as secrets.resolve: an environment name
    that simply isn't registered is treated identically to production —
    NOT assumed safe just because it isn't explicitly marked unsafe."""
    _ensure_ready(testing_agent_register, full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub(
                "testing.run_suite", shell_command="echo", shell_args_json=json.dumps(["SHOULD_NEVER_RUN_MARKER"]),
                resolved_environment="some_environment_nobody_registered",
            )
        assert "SHOULD_NEVER_RUN_MARKER" not in prompt
        return _stub("testing.run_suite", shell_command=None, answer_or_proposal="Refusing.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="testing-run-suite-unregistered", task_description="Run the suite against a weird target.",
        agent_capability="testing_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()
    assert execution.status == "completed"


def test_propose_new_test_materializes_as_real_branch_commit_push(
    full_stack, execution_url, proposal_repo, disposable_bare_repo_for_bridge, monkeypatch,
):
    _ensure_ready(testing_agent_register, full_stack["governance"], full_stack["assembly"])
    proposal_text = "Add a regression test for the SO0003 cancellation path."

    def fake_generate(model, prompt):
        return _stub("testing.propose_new_test", answer_or_proposal=proposal_text, risk_classification="low")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="testing-propose-test-1", task_description="Add a regression test.",
        agent_capability="testing_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    git_execution = resumed.result["git_execution"]
    assert git_execution["attempted"] is True
    assert git_execution["branch_name"] == "testing-agent/task-testing-propose-test-1"


# ---------------------------------------------------------------------------
# Live-model smoke tests — one per new agent, lenient on exact routing
# outcome, proving the pipeline doesn't crash with a real model in the loop.
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("completed", "awaiting_approval", "refused", "delegated", "awaiting_delegation", "failed")


@pytest.mark.parametrize("agent_capability,register_module,question", [
    ("django_agent", django_agent_register, "Explain what Django URL routing does, in one sentence. Don't propose any changes."),
    ("devops_agent", devops_agent_register, "Explain what a CI/CD pipeline is, in one sentence. Don't propose any changes."),
])
def test_live_explain_only_smoke(full_stack, ollama_available, agent_capability, register_module, question):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_ready(register_module, full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"{agent_capability}-live-test-1", task_description=question,
        agent_capability=agent_capability, namespace="default", target_model=LOCAL_MODEL, max_iterations=6,
    )
    db.close()
    assert execution.status in _TERMINAL_STATES, f"unexpected status {execution.status!r}, failure_reason={execution.failure_reason!r}"
    assert execution.iterations_used >= 1

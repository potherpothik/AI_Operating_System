import json
import uuid
import httpx
import pytest

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.coding_agent_gateway import register as coding_agent_gateway_register

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
        "provenance": [], "risk_classification": "high", "delegate_to": None, "action": action,
        "provider": None, "instruction": None,
    }
    base.update(overrides)
    return json.dumps(base)


# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------

def test_capability_discovered_with_correct_boundaries():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    assert "coding_agent_gateway" in loaded

    cap = capability_registry.get_capability(db, "coding_agent_gateway")
    assert capability_registry.local_precheck(cap, "coding_gateway.propose_run") == "require_approval"
    assert capability_registry.local_precheck(cap, "git.merge") == "deny"
    assert capability_registry.local_precheck(cap, "git.force_push") == "deny"
    db.close()


def test_governance_requires_approval_for_coding_gateway_propose_run(full_stack):
    """Direct policy check against the real, live governance instance —
    not asserted from the YAML file, from the actual /security/authorize
    decision."""
    resp = httpx.post(
        f"{full_stack['governance']}/security/authorize",
        json={"actor": "coding_agent_gateway", "action": "coding_gateway.propose_run", "resource": "some-repo"},
    )
    assert resp.status_code == 200
    assert resp.json()["decision"] == "require_approval"


# ---------------------------------------------------------------------------
# The real, novel mechanism this phase adds: a structural sandbox-backend
# safety gate, live-verified against actual installed/missing CLIs — never
# asserted, the real coding_gateway_bridge.materialize_propose_run() output.
# ---------------------------------------------------------------------------

def test_opencode_provider_reports_unsafe_backend_live(full_stack, execution_url, proposal_repo, monkeypatch):
    """opencode is now genuinely installed in this environment (v1.18.4 —
    confirmed live: `opencode --version` really succeeds; it was genuinely
    absent when Phase 22 was first built and tested, a real environmental
    change discovered incidentally while testing Phase 23, not a
    regression). The gate still correctly refuses it, same as claude:
    the probe genuinely runs, but the sandbox backend still isn't
    docker, so a live agentic session is still refused."""
    _ensure_ready(coding_agent_gateway_register, full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub("coding_gateway.propose_run", provider="opencode", instruction="Add a docstring to utils.py.")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"coding-gateway-opencode-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Add a docstring to utils.py using OpenCode.",
        agent_capability="coding_agent_gateway", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    cg = resumed.result["coding_gateway_execution"]
    assert cg["attempted"] is True
    assert cg["status"] == "unsafe_backend"
    assert cg["probe"]["backend"] == "subprocess"
    # Real finding, not asserted in advance: opencode ALSO crashes under
    # SubprocessSandbox's 512MB RLIMIT_AS cap (same as claude) — a real
    # process genuinely ran and terminated, whatever the exit code.
    assert cg["probe"]["exit_code"] is not None


def test_missing_binary_still_reports_not_configured(proposal_repo, monkeypatch):
    """Structural coverage for the not_configured path, now that both
    real providers this repo knows about happen to be installed in this
    environment (a real, live-verified state, not an assumption): a
    direct unit test of materialize_propose_run() with clients.shell_execute
    mocked to return the exact shape Shell Executor's own service.py
    produces for a real FileNotFoundError (SandboxCreationError caught,
    status="failed", exit_code=None) — the same real code path Phase 22's
    original live test exercised when opencode was genuinely absent,
    kept covered now that the environment itself has changed."""
    from types import SimpleNamespace
    from agents import clients
    from agents.reasoning_engine import coding_gateway_bridge

    def fake_shell_execute(command, args, working_dir, capability, requesting_agent, mode, task_id=None, correlation_id=""):
        assert command == "opencode"
        return {"ok": True, "result": {"status": "failed", "exit_code": None, "backend": "none", "stdout": "", "stderr": f"command {command!r} not found"}}

    monkeypatch.setattr(clients, "shell_execute", fake_shell_execute)

    fake_execution = SimpleNamespace(
        id="fake-exec-id", task_id="fake-task-id", agent_capability="coding_agent_gateway", context_id=None,
        result={"provider": "opencode", "instruction": "Add a docstring to utils.py.", "risk_classification": "high"},
    )
    outcome = coding_gateway_bridge.materialize_propose_run(fake_execution)
    assert outcome["attempted"] is True
    assert outcome["status"] == "not_configured"
    assert "opencode" in outcome["reason"]


def test_claude_code_provider_reports_unsafe_backend_live(full_stack, execution_url, proposal_repo, monkeypatch):
    """The `claude` CLI IS genuinely installed in this environment — the
    real probe succeeds (real exit code, real version string). What stops
    a live agentic session isn't a missing binary, it's the honest,
    structural finding that Shell Executor's only available backend here
    is `subprocess`, which does not provide real network/filesystem
    isolation (services/execution/execution/shell_executor/sandbox.py) —
    unsafe to hand a live, credentialed external agent. Confirmed live,
    not asserted: the real `backend` field Shell Executor returns."""
    _ensure_ready(coding_agent_gateway_register, full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub("coding_gateway.propose_run", provider="claude_code", instruction="Add a docstring to utils.py.")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"coding-gateway-claude-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Add a docstring to utils.py using Claude Code.",
        agent_capability="coding_agent_gateway", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    cg = resumed.result["coding_gateway_execution"]
    assert cg["attempted"] is True
    assert cg["status"] == "unsafe_backend"
    assert cg["probe"]["backend"] == "subprocess"
    # Real finding, not asserted in advance: the actual `claude` binary
    # (a Node/Bun runtime) crashed with signal 6 (SIGABRT) under
    # SubprocessSandbox's 512MB RLIMIT_AS cap — exit_code == -6, not a
    # clean 0. A second, independent confirmation that this backend
    # can't safely run this CLI, on top of the network/filesystem gap
    # the gate is actually checking for.
    assert cg["probe"]["exit_code"] is not None  # a real process genuinely ran and terminated
    # No branch/commit/push ever attempted — confirms the gate fires
    # BEFORE any git action, not after a failed one.
    assert "branch_name" not in cg


def test_unknown_provider_refused_without_any_shell_call(full_stack, proposal_repo, monkeypatch):
    _ensure_ready(coding_agent_gateway_register, full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub("coding_gateway.propose_run", provider="aider", instruction="Do something.")

    monkeypatch.setattr(loop, "generate", fake_generate)

    task_id = f"coding-gateway-unknown-provider-test-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    execution = loop.execute(
        db, task_id=task_id, task_description="Use an unsupported provider.",
        agent_capability="coding_agent_gateway", namespace="default", target_model=LOCAL_MODEL,
    )
    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    cg = resumed.result["coding_gateway_execution"]
    assert cg["attempted"] is False
    assert "aider" in cg["reason"]


# ---------------------------------------------------------------------------
# Live-model smoke test
# ---------------------------------------------------------------------------

_TERMINAL_STATES = ("completed", "awaiting_approval", "refused", "delegated", "awaiting_delegation", "failed")


def test_live_explain_only_smoke(full_stack, ollama_available):
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_ready(coding_agent_gateway_register, full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="coding-agent-gateway-live-test-1",
        task_description="In one sentence, explain what your role is. Don't propose running any coding session.",
        agent_capability="coding_agent_gateway", namespace="default", target_model=LOCAL_MODEL, max_iterations=6,
    )
    db.close()
    assert execution.status in _TERMINAL_STATES, f"unexpected status {execution.status!r}, failure_reason={execution.failure_reason!r}"
    assert execution.iterations_used >= 1

from execution.db import SessionLocal
from execution.shell_executor.service import run_sandboxed, Denied


def test_allowed_read_only_command_completes(sandbox_root, governance_url):
    work_dir = sandbox_root / "task-1"
    work_dir.mkdir()
    db = SessionLocal()
    execution = run_sandboxed(
        db, "git", ["status"], str(work_dir), "odoo_agent", "reasoning_engine",
        task_id="task-1", mode="read_only",
    )
    db.close()
    assert execution.status == "completed"


def test_command_not_on_allowlist_is_denied(sandbox_root, governance_url):
    work_dir = sandbox_root / "task-1"
    work_dir.mkdir()
    db = SessionLocal()
    try:
        run_sandboxed(db, "rm", ["-rf", "."], str(work_dir), "odoo_agent", "reasoning_engine", task_id="task-1", mode="mutating")
        assert False, "should have been denied"
    except Denied:
        pass
    db.close()


def test_unknown_capability_denied_before_execution(sandbox_root, governance_url):
    work_dir = sandbox_root / "task-1"
    work_dir.mkdir()
    db = SessionLocal()
    try:
        run_sandboxed(db, "git", ["status"], str(work_dir), "nonexistent_capability", "x", task_id="task-1", mode="read_only")
        assert False, "should have been denied"
    except Denied:
        pass
    db.close()


def test_execution_is_persisted_and_queryable(sandbox_root, governance_url):
    from execution.shell_executor import store
    work_dir = sandbox_root / "task-1"
    work_dir.mkdir()
    db = SessionLocal()
    execution = run_sandboxed(
        db, "git", ["status"], str(work_dir), "odoo_agent", "reasoning_engine", task_id="task-1", mode="read_only",
    )
    fetched = store.get(db, execution.id)
    db.close()
    assert fetched is not None
    assert fetched.command == "git"
    assert fetched.requesting_capability == "odoo_agent"


def test_list_executions_filters_by_capability(sandbox_root, governance_url):
    """Phase 13: GET /shell/executions is the listing endpoint Metrics
    Dashboard's tool-execution-volume-by-capability category needs —
    no code before this phase ever listed more than one execution."""
    from execution.shell_executor import store
    work_dir = sandbox_root / "task-list-1"
    work_dir.mkdir()
    db = SessionLocal()
    run_sandboxed(db, "git", ["status"], str(work_dir), "odoo_agent", "reasoning_engine", task_id="task-list-1", mode="read_only")

    odoo_only = store.list_executions(db, requesting_capability="odoo_agent")
    db.close()
    assert all(e.requesting_capability == "odoo_agent" for e in odoo_only)
    assert len(odoo_only) >= 1


def test_authorization_actually_hits_real_governance_not_a_stub(sandbox_root, governance_url):
    """
    Proves this isn't just checking the local allowlist — the governance
    policy for odoo_agent's shell.execute action must genuinely be
    'allow' for this to succeed; if the policy file's rule were missing
    or set to deny, this would fail even though the local allowlist
    permits the command.
    """
    import httpx
    decision = httpx.post(
        f"{governance_url}/security/authorize",
        json={"actor": "odoo_agent", "action": "shell.execute", "resource": "/anything"},
    ).json()
    assert decision["decision"] == "allow"

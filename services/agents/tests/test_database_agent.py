import json
import httpx
import pytest
import sqlalchemy

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.database_agent import register as database_agent_register

LOCAL_MODEL = "qwen3.5:4b"


def _ensure_database_agent_ready(governance_url, assembly_url):
    db = SessionLocal()
    capability_registry.load_all(db)
    db.close()

    result = database_agent_register.ensure_template_registered(created_by="test-suite")
    if result["registered"]:
        approval_id = result["result"]["approval_id"]
        httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")


def _stub_response(**overrides):
    base = {
        "reasoning": "test reasoning", "answer_or_proposal": "test answer", "confidence": 0.9,
        "provenance": [], "risk_classification": "informational", "delegate_to": None,
        "action": None, "target_db": None, "sql_template": None, "params_json": None,
        "table": None, "impact_estimate": None, "target_platform": None,
    }
    base.update(overrides)
    return json.dumps(base)


def test_db_read_tool_call_round_trip_returns_real_data(full_stack, database_url, monkeypatch):
    """
    A single-turn db.read: the model asks to read, Reasoning Engine
    actually calls Database Connector, and the SECOND turn's prompt
    genuinely contains the real row data — proving this isn't a canned
    response, by asserting on the exact seeded value.
    """
    _ensure_database_agent_ready(full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            assert "SO0001" not in prompt  # not yet — this IS the read request itself
            return _stub_response(
                action="db.read", target_db="demo_erp", table="sale_order",
                sql_template="SELECT name, amount_total FROM sale_order WHERE id = :id",
                params_json=json.dumps({"id": 1}),
            )
        # second call: the real query result must now be in the prompt
        assert "SO0001" in prompt
        return _stub_response(
            action="db.read", sql_template="", answer_or_proposal="Sale order 1 is SO0001, amount 1250.00.",
            risk_classification="informational",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="db-read-test-1", task_description="What is sale order 1?",
        agent_capability="database_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2


def test_schema_invalid_retry_does_not_discard_earlier_tool_call_context(full_stack, database_url, monkeypatch):
    """
    Regression test: a schema-invalid response one iteration after a
    successful db.read tool call used to rebuild the retry prompt from
    the ORIGINAL task_description rather than current_task_description —
    silently discarding the real query result the model had just been
    given, so a retry would have the model reasoning from nothing. Caught
    by a live model doing exactly this in test_live_database_agent_read_question
    (a live model's None answer_or_proposal triggered the retry path,
    which then lost the SO0001 data injected the iteration before).
    """
    _ensure_database_agent_ready(full_stack["governance"], full_stack["assembly"])
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub_response(
                action="db.read", target_db="demo_erp", table="sale_order",
                sql_template="SELECT name, amount_total FROM sale_order WHERE id = :id",
                params_json=json.dumps({"id": 1}),
            )
        if calls["count"] == 2:
            assert "SO0001" in prompt  # tool result present before the bad response
            return json.dumps({"reasoning": "x", "action": "db.read"})  # missing required fields -> schema-invalid
        # third call: the retry prompt must STILL contain the tool result,
        # not just the schema-validation-error text
        assert "SO0001" in prompt
        return _stub_response(action="db.read", sql_template="", answer_or_proposal="It's SO0001.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="db-read-retry-test", task_description="What is sale order 1?",
        agent_capability="database_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert calls["count"] == 3


def test_dry_run_then_propose_write_then_approve_executes_real_write(full_stack, database_url, demo_erp_clean, monkeypatch):
    """
    The Phase 7 doc's Section 3 diagram end to end: dry_run tool call ->
    real impact estimate fed back -> propose_write with that estimate ->
    approval -> resume -> a REAL write lands in the disposable demo_erp
    database, verified independently by querying it directly afterward.
    """
    _ensure_database_agent_ready(full_stack["governance"], full_stack["assembly"])
    sql_template = "UPDATE sale_order SET state = :state WHERE name = :name"
    params_json = json.dumps({"state": "cancel", "name": "SO0003"})
    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub_response(action="db.dry_run", target_db="demo_erp", sql_template=sql_template, params_json=params_json)
        assert "row(s) affected" in prompt  # the real dry-run estimate must be in context now
        return _stub_response(
            action="db.propose_write", target_db="demo_erp", sql_template=sql_template, params_json=params_json,
            impact_estimate="1 row affected per the dry-run", risk_classification="medium",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="db-write-test-1", task_description="Cancel sale order SO0003.",
        agent_capability="database_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"
    assert execution.result["dry_run_id"]  # system-tracked, not model-supplied

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    db_execution = resumed.result["db_execution"]
    assert db_execution["attempted"] is True
    assert db_execution["result"]["ok"] is True
    assert db_execution["result"]["status"] == "completed"

    target_engine = sqlalchemy.create_engine("postgresql://saadi:devpassword@localhost:5432/demo_erp")
    with target_engine.connect() as conn:
        state = conn.execute(sqlalchemy.text("SELECT state FROM sale_order WHERE name = 'SO0003'")).scalar()
    assert state == "cancel"


def test_propose_write_without_a_prior_dry_run_cannot_execute(full_stack, database_url, demo_erp_clean, monkeypatch):
    """
    A model that skips straight to db.propose_write without ever calling
    db.dry_run first still gets routed to approval (risk_classification
    alone drives that), but resume() has no dry_run_id to reference and
    must refuse to execute — dry-run isn't advisory (Phase 7 doc).
    """
    _ensure_database_agent_ready(full_stack["governance"], full_stack["assembly"])
    sql_template = "UPDATE sale_order SET state = :state WHERE name = :name"
    params_json = json.dumps({"state": "cancel", "name": "SO0003"})

    def fake_generate(model, prompt):
        return _stub_response(
            action="db.propose_write", target_db="demo_erp", sql_template=sql_template, params_json=params_json,
            impact_estimate="unknown", risk_classification="medium",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="db-write-no-dryrun", task_description="Cancel sale order SO0003.",
        agent_capability="database_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"
    assert "dry_run_id" not in (execution.result or {})

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.result["db_execution"]["attempted"] is False

    target_engine = sqlalchemy.create_engine("postgresql://saadi:devpassword@localhost:5432/demo_erp")
    with target_engine.connect() as conn:
        state = conn.execute(sqlalchemy.text("SELECT state FROM sale_order WHERE name = 'SO0003'")).scalar()
    assert state == "sale"  # demo_erp_clean's setup state — nothing executed


def test_propose_migration_approved_reaches_the_real_migration_adapter(full_stack, database_url, monkeypatch):
    """
    This test's job is the WIRING: an approved db.propose_migration must
    reach the real Database Connector's /db/migrate over real HTTP and
    come back with a genuine structured response — not verifying the
    file-generation mechanics themselves, which Phase 7's own test suite
    (test_migration_adapter.py) already covers in-process with a real
    configured DJANGO_PROJECT_PATH. That can't be injected here: the
    database service is a separately-running process by the time this
    test runs (session-scoped, like execution_url), so a per-test env var
    set from this process never reaches it — same class of constraint as
    Phase 6's proposal_repo fixture. The live server's actual environment
    has no Django project configured, so "not_configured" IS the correct,
    honest answer here — not a failure to work around.
    """
    _ensure_database_agent_ready(full_stack["governance"], full_stack["assembly"])

    def fake_generate(model, prompt):
        return _stub_response(
            action="db.propose_migration", target_platform="django",
            answer_or_proposal="Add a discount_pct column to sale_order",
            risk_classification="high",
        )

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="db-migrate-test-1", task_description="Add a discount percentage field to sale orders.",
        agent_capability="database_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    assert execution.status == "awaiting_approval"

    httpx.post(f"{full_stack['governance']}/approval/{execution.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    resumed = loop.resume(db, execution.id)
    db.close()

    assert resumed.status == "completed"
    db_execution = resumed.result["db_execution"]
    assert db_execution["attempted"] is True
    migrate_result = db_execution["result"]
    assert migrate_result["ok"] is True  # a real, well-formed response from the connector
    assert migrate_result["status"] in ("generated", "not_configured")
    assert migrate_result["status"] == "not_configured"  # honest given this environment's actual config


def test_live_database_agent_read_question(full_stack, database_url, ollama_available):
    """One real live-model smoke test — lenient about the exact routing
    outcome (a live model won't phrase things identically every run) but
    proves the whole pipeline doesn't crash with a real model in the loop."""
    if not ollama_available:
        pytest.skip("Ollama not reachable at OLLAMA_URL")
    _ensure_database_agent_ready(full_stack["governance"], full_stack["assembly"])

    db = SessionLocal()
    execution = loop.execute(
        db, task_id="db-live-test-1", task_description="How many sale orders does partner 1 have? Just tell me, don't propose any changes.",
        agent_capability="database_agent", namespace="default", target_model=LOCAL_MODEL, max_iterations=6,
    )
    db.close()
    # "failed" (schema-validation exhausted after retries) is an
    # acceptable, non-crashing terminal state here too — the actual
    # multi-field, multi-turn schema is a lot to ask a live small model
    # to hit perfectly every run, and the point of this test is that the
    # pipeline never crashes, not that the model phrases things exactly
    # right on the first live attempt.
    assert execution.status in ("completed", "awaiting_approval", "refused", "delegated", "awaiting_delegation", "failed"), (
        f"unexpected status {execution.status!r}, failure_reason={execution.failure_reason!r}"
    )
    assert execution.iterations_used >= 1

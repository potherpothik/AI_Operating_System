from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_unknown_role_denies_by_default():
    r = client.post(
        "/security/authorize",
        json={"actor": "nonexistent_role", "action": "anything.at_all", "resource": "*"},
    )
    assert r.json()["decision"] == "deny"


def test_odoo_agent_can_read():
    r = client.post(
        "/security/authorize",
        json={"actor": "odoo_agent", "action": "odoo.read_orm", "resource": "sale.order"},
    )
    assert r.json()["decision"] == "allow"


def test_odoo_agent_propose_change_requires_approval():
    r = client.post(
        "/security/authorize",
        json={"actor": "odoo_agent", "action": "odoo.propose_change", "resource": "sale.order"},
    )
    assert r.json()["decision"] == "require_approval"


def test_odoo_agent_write_orm_denied():
    r = client.post(
        "/security/authorize",
        json={"actor": "odoo_agent", "action": "odoo.write_orm", "resource": "sale.order"},
    )
    assert r.json()["decision"] == "deny"


def test_odoo_agent_shell_execute_allowed():
    r = client.post(
        "/security/authorize",
        json={"actor": "odoo_agent", "action": "shell.execute", "resource": "/tmp/ai_os_sandbox/task-1"},
    )
    assert r.json()["decision"] == "allow"


def test_odoo_agent_git_actions_allowed():
    for action in ("git.branch", "git.commit", "git.diff", "git.push", "git.open_mr"):
        r = client.post(
            "/security/authorize",
            json={"actor": "odoo_agent", "action": action, "resource": "AI_Operating_System"},
        )
        assert r.json()["decision"] == "allow", f"{action} expected allow, got {r.json()}"


def test_database_agent_read_and_dry_run_allowed():
    for action in ("db.read", "db.dry_run"):
        r = client.post("/security/authorize", json={"actor": "database_agent", "action": action, "resource": "demo_erp"})
        assert r.json()["decision"] == "allow", f"{action} expected allow, got {r.json()}"


def test_database_agent_write_and_migration_require_approval():
    for action in ("db.propose_write", "db.propose_migration"):
        r = client.post("/security/authorize", json={"actor": "database_agent", "action": action, "resource": "demo_erp"})
        assert r.json()["decision"] == "require_approval", f"{action} expected require_approval, got {r.json()}"


def test_database_agent_connector_execution_actions_allowed():
    for action in ("db.write", "db.migrate"):
        r = client.post("/security/authorize", json={"actor": "database_agent", "action": action, "resource": "demo_erp"})
        assert r.json()["decision"] == "allow", f"{action} expected allow, got {r.json()}"


def test_database_agent_direct_write_and_ddl_denied():
    for action in ("db.write_direct", "db.ddl_direct"):
        r = client.post("/security/authorize", json={"actor": "database_agent", "action": action, "resource": "demo_erp"})
        assert r.json()["decision"] == "deny", f"{action} expected deny, got {r.json()}"


def test_planner_plan_and_replan_allowed():
    for action in ("planner.plan", "planner.replan"):
        r = client.post("/security/authorize", json={"actor": "planner", "action": action, "resource": "task-1"})
        assert r.json()["decision"] == "allow", f"{action} expected allow, got {r.json()}"


def test_planner_new_capability_registration_allowed():
    r = client.post("/security/authorize", json={"actor": "planner", "action": "capability.register_new", "resource": "some_agent"})
    assert r.json()["decision"] == "allow"


def test_planner_capability_scope_change_requires_approval():
    r = client.post("/security/authorize", json={"actor": "planner", "action": "capability.change_scope", "resource": "odoo_agent"})
    assert r.json()["decision"] == "require_approval"


def test_planner_capability_deprecation_requires_approval():
    r = client.post("/security/authorize", json={"actor": "planner", "action": "capability.deprecate", "resource": "odoo_agent"})
    assert r.json()["decision"] == "require_approval"


def test_human_admin_wildcard_allow():
    r = client.post(
        "/security/authorize",
        json={"actor": "human_admin", "action": "anything.here", "resource": "anything"},
    )
    assert r.json()["decision"] == "allow"


def test_classify_plain_content_stays_at_declared_tier():
    r = client.post("/security/classify", json={"content": "the sale.order model tracks order state"})
    body = r.json()
    assert body["classification"] == "internal"
    assert body["heuristic_floor"] == "public"


def test_classify_detects_secret_pattern_and_raises_floor():
    r = client.post(
        "/security/classify",
        json={"content": "api_key: sk-abcdef123456", "declared_classification": "public"},
    )
    body = r.json()
    assert body["classification"] == "confidential"
    assert body["heuristic_floor"] == "confidential"


def test_classify_never_lowers_a_higher_declared_tier():
    r = client.post(
        "/security/classify",
        json={"content": "nothing sensitive here", "declared_classification": "confidential"},
    )
    assert r.json()["classification"] == "confidential"

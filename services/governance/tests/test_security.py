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

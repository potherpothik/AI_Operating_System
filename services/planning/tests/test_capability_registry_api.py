import httpx

from planning.db import SessionLocal
from planning.capability_registry import api, loader, store
from planning.capability_registry.models import CapabilityRegistryEntry


def test_sync_discovers_real_agents_from_live_service(governance_url, agents_url):
    db = SessionLocal()
    results = loader.sync_from_agents(db)
    entries = store.list_all(db)
    db.close()

    assert "odoo_agent" in results["registered_new"]
    assert "database_agent" in results["registered_new"]
    agent_names = {e.agent_capability for e in entries}
    assert {"odoo_agent", "database_agent"}.issubset(agent_names)


def test_sync_is_idempotent_on_second_run(governance_url, agents_url):
    db = SessionLocal()
    loader.sync_from_agents(db)
    second = loader.sync_from_agents(db)
    db.close()
    assert "odoo_agent" in second["unchanged"]
    assert "odoo_agent" not in second["registered_new"]


def test_synced_entry_matches_real_capability_yaml_content(governance_url, agents_url):
    db = SessionLocal()
    loader.sync_from_agents(db)
    entry = store.get_active(db, "odoo_agent")
    db.close()
    assert entry.allowed_actions == ["odoo.read_orm", "odoo.read_orm_live", "odoo.explain_rule", "odoo.propose_change"]
    assert entry.classification_ceiling == "internal"


def test_scope_change_requires_real_governance_approval(governance_url, agents_url):
    db = SessionLocal()
    store.create_active(db, "fake_agent_for_scope_test", ["old.action"], [], [], "internal")
    db.close()

    db = SessionLocal()
    req = api.RegisterRequest(agent_capability="fake_agent_for_scope_test", allowed_actions=["new.action"], classification_ceiling="internal")
    result = api.register_capability(req, db)
    db.close()

    assert result["status"] == "pending_approval"
    assert result["version"] == "2"

    db = SessionLocal()
    still_old = store.get_active(db, "fake_agent_for_scope_test")
    db.close()
    assert still_old.allowed_actions == ["old.action"]  # not silently applied


def test_scope_change_takes_effect_only_after_approval(governance_url, agents_url):
    db = SessionLocal()
    store.create_active(db, "fake_agent_for_approval_test", ["old.action"], [], [], "internal")
    req = api.RegisterRequest(agent_capability="fake_agent_for_approval_test", allowed_actions=["new.action"], classification_ceiling="internal")
    result = api.register_capability(req, db)
    db.close()

    entry_id = result["id"]
    db = SessionLocal()
    approval_id = db.get(CapabilityRegistryEntry, entry_id).approval_id
    db.close()

    httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})

    db = SessionLocal()
    updated = loader.reconcile_pending(db)
    active = store.get_active(db, "fake_agent_for_approval_test")
    db.close()

    assert any(u["agent_capability"] == "fake_agent_for_approval_test" and u["status"] == "active" for u in updated)
    assert active.allowed_actions == ["new.action"]


def test_deprecation_requires_approval_and_only_takes_effect_after(governance_url, agents_url):
    db = SessionLocal()
    entry = store.create_active(db, "fake_agent_for_deprecate_test", ["old.action"], [], [], "internal")
    db.close()

    db = SessionLocal()
    result = api.deprecate_capability(entry.id, api.DeprecateRequest(requested_by="planner"), db)
    db.close()
    assert result["status"] == "pending_approval"

    db = SessionLocal()
    still_active = store.get_active(db, "fake_agent_for_deprecate_test")
    db.close()
    assert still_active is not None  # not deprecated yet

    httpx.post(f"{governance_url}/approval/{result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})

    db = SessionLocal()
    confirmed = api.confirm_deprecation(entry.id, db)
    no_longer_active = store.get_active(db, "fake_agent_for_deprecate_test")
    db.close()
    assert confirmed["status"] == "deprecated"
    assert no_longer_active is None

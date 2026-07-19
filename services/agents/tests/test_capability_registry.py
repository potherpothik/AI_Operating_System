from agents.db import SessionLocal
from agents.reasoning_engine import capability_registry


def test_load_all_discovers_odoo_agent():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    assert "odoo_agent" in loaded
    cap = capability_registry.get_capability(db, "odoo_agent")
    assert cap.allowed_actions == ["odoo.read_orm", "odoo.explain_rule", "odoo.propose_change"]
    assert cap.forbidden_actions == ["odoo.write_orm", "odoo.execute_migration"]
    assert cap.requires_approval == ["odoo.propose_change"]
    assert cap.template_id == "odoo_agent"
    db.close()


def test_load_all_discovers_database_agent():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    assert "database_agent" in loaded
    cap = capability_registry.get_capability(db, "database_agent")
    assert cap.allowed_actions == ["db.read", "db.dry_run", "db.propose_write", "db.propose_migration"]
    assert cap.forbidden_actions == ["db.write_direct", "db.ddl_direct"]
    assert cap.requires_approval == ["db.propose_write", "db.propose_migration"]
    assert cap.template_id == "database_agent"
    db.close()


def test_load_all_discovers_planner():
    db = SessionLocal()
    loaded = capability_registry.load_all(db)
    assert "planner" in loaded
    cap = capability_registry.get_capability(db, "planner")
    assert cap.allowed_actions == ["planner.plan", "planner.replan"]
    assert cap.classification_ceiling == "confidential"
    assert cap.template_id == "planner"
    db.close()


def test_load_all_is_idempotent():
    # Deliberately not a hardcoded count — genuine idempotency means
    # running load_all() twice in a row doesn't create duplicate rows,
    # regardless of how many agents happen to be registered right now.
    db = SessionLocal()
    capability_registry.load_all(db)
    count_before = db.query(capability_registry.AgentCapabilityDef).count()
    capability_registry.load_all(db)
    count_after = db.query(capability_registry.AgentCapabilityDef).count()
    assert count_before == count_after
    assert count_before >= 3  # odoo_agent, database_agent, planner all exist by now
    db.close()


def test_local_precheck_read_orm_is_allowed():
    db = SessionLocal()
    capability_registry.load_all(db)
    cap = capability_registry.get_capability(db, "odoo_agent")
    assert capability_registry.local_precheck(cap, "odoo.read_orm") == "allow"
    db.close()


def test_local_precheck_propose_change_requires_approval():
    db = SessionLocal()
    capability_registry.load_all(db)
    cap = capability_registry.get_capability(db, "odoo_agent")
    assert capability_registry.local_precheck(cap, "odoo.propose_change") == "require_approval"
    db.close()


def test_local_precheck_write_orm_is_denied():
    db = SessionLocal()
    capability_registry.load_all(db)
    cap = capability_registry.get_capability(db, "odoo_agent")
    assert capability_registry.local_precheck(cap, "odoo.write_orm") == "deny"
    db.close()


def test_local_precheck_unknown_action_is_denied_by_default():
    db = SessionLocal()
    capability_registry.load_all(db)
    cap = capability_registry.get_capability(db, "odoo_agent")
    assert capability_registry.local_precheck(cap, "odoo.something_never_declared") == "deny"
    db.close()

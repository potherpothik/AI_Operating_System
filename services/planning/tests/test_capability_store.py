from planning.db import SessionLocal
from planning.capability_registry import store


def test_create_active_and_get_active():
    db = SessionLocal()
    store.create_active(db, "test_cap_1", ["a.read"], [], [], "internal")
    active = store.get_active(db, "test_cap_1")
    db.close()
    assert active is not None
    assert active.version == "1"
    assert active.status == "active"


def test_scope_matches_ignores_list_order():
    db = SessionLocal()
    entry = store.create_active(db, "test_cap_2", ["a.read", "a.write"], ["a.ddl"], ["a.write"], "internal")
    db.close()
    assert store.scope_matches(entry, ["a.write", "a.read"], ["a.ddl"], ["a.write"], "internal") is True


def test_scope_matches_detects_real_change():
    db = SessionLocal()
    entry = store.create_active(db, "test_cap_3", ["a.read"], [], [], "internal")
    db.close()
    assert store.scope_matches(entry, ["a.read", "a.write"], [], [], "internal") is False
    assert store.scope_matches(entry, ["a.read"], [], [], "confidential") is False


def test_activate_supersedes_previous_active_version():
    db = SessionLocal()
    v1 = store.create_active(db, "test_cap_4", ["a.read"], [], [], "internal", version="1")
    v2 = store.create_pending(db, "test_cap_4", ["a.read", "a.write"], [], [], "internal", "2", approval_id="fake-approval")
    v1_id, v2_id = v1.id, v2.id  # captured before the session closes — detached instances can't lazy-load
    store.activate(db, v2_id)
    db.close()

    db = SessionLocal()
    refreshed_v1 = store.get(db, v1_id)
    refreshed_v2 = store.get(db, v2_id)
    active = store.get_active(db, "test_cap_4")
    db.close()

    assert refreshed_v1.status == "superseded"
    assert refreshed_v2.status == "active"
    assert active.id == v2_id


def test_list_all_filters_by_action_type():
    db = SessionLocal()
    store.create_active(db, "test_cap_5", ["unique_action_xyz"], [], [], "internal")
    store.create_active(db, "test_cap_6", ["other_action"], [], [], "internal")
    matches = store.list_all(db, action_type="unique_action_xyz")
    db.close()
    assert len(matches) == 1
    assert matches[0].agent_capability == "test_cap_5"


def test_deprecate_pending_holds_active_until_finalized():
    db = SessionLocal()
    entry = store.create_active(db, "test_cap_7", ["a.read"], [], [], "internal")
    store.deprecate_pending(db, "test_cap_7", "fake-approval")
    still_active = store.get_active(db, "test_cap_7")
    db.close()
    assert still_active is not None
    assert still_active.status == "active"


def test_finalize_deprecation_marks_deprecated():
    db = SessionLocal()
    entry = store.create_active(db, "test_cap_8", ["a.read"], [], [], "internal")
    store.finalize_deprecation(db, entry.id)
    no_longer_active = store.get_active(db, "test_cap_8")
    deprecated = store.get(db, entry.id)
    db.close()
    assert no_longer_active is None
    assert deprecated.status == "deprecated"
    assert deprecated.deprecated_at is not None

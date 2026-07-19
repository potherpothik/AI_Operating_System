import pytest

from platform_spine.db import SessionLocal
from platform_spine.task_manager import store
from platform_spine.task_manager.state_machine import validate_transition, InvalidTransition


def test_valid_transitions_do_not_raise():
    validate_transition("queued", "in_progress")
    validate_transition("in_progress", "review")
    validate_transition("review", "done")


def test_invalid_transition_raises():
    with pytest.raises(InvalidTransition):
        validate_transition("queued", "done")  # can't skip straight to done


def test_terminal_states_have_no_outgoing_transitions():
    with pytest.raises(InvalidTransition):
        validate_transition("done", "in_progress")
    with pytest.raises(InvalidTransition):
        validate_transition("failed", "queued")


def test_enqueue_creates_task_in_queued_status():
    db = SessionLocal()
    task = store.enqueue(
        db, title="test task", description="", requested_by="odoo_agent",
        correlation_id="corr-1",
    )
    assert task.status == "queued"
    events = store.task_events(db, task.id)
    assert len(events) == 1
    assert events[0].to_status == "queued"
    db.close()


def test_update_status_records_event_and_rejects_invalid_transition():
    db = SessionLocal()
    task = store.enqueue(db, title="t", description="", requested_by="odoo_agent", correlation_id="corr-2")

    updated, error = store.update_status(db, task.id, "in_progress", actor="reasoning_engine")
    assert error is None
    assert updated.status == "in_progress"

    _, error = store.update_status(db, task.id, "queued", actor="reasoning_engine")
    assert error is not None  # in_progress -> queued isn't a valid transition
    db.close()


def test_dequeue_only_returns_queued_tasks():
    db = SessionLocal()
    t1 = store.enqueue(db, title="a", description="", requested_by="odoo_agent", correlation_id="c1")
    t2 = store.enqueue(db, title="b", description="", requested_by="odoo_agent", correlation_id="c2")
    store.update_status(db, t2.id, "in_progress", actor="x")

    queued = store.dequeue(db)
    ids = {t.id for t in queued}
    assert t1.id in ids
    assert t2.id not in ids
    db.close()


def test_list_tasks_filters_by_status():
    db = SessionLocal()
    t1 = store.enqueue(db, title="a", description="", requested_by="odoo_agent", correlation_id="c1")
    store.update_status(db, t1.id, "in_progress", actor="x")
    store.enqueue(db, title="b", description="", requested_by="odoo_agent", correlation_id="c2")

    in_progress = store.list_tasks(db, status="in_progress")
    assert len(in_progress) == 1
    assert in_progress[0].id == t1.id
    db.close()


def test_task_timestamps_survive_round_trip_as_the_same_utc_instant():
    """
    Same class of bug found in Phase 1: a non-timezone-aware DateTime
    column silently shifted stored values under a non-UTC Postgres
    session. Task.created_at / TaskEvent.ts use DateTime(timezone=True)
    from the start here — this locks that in as a permanent check.
    """
    from datetime import datetime, timezone as tz

    db = SessionLocal()
    before = datetime.now(tz.utc)
    task = store.enqueue(db, title="t", description="", requested_by="odoo_agent", correlation_id="c3")
    after = datetime.now(tz.utc)

    created = task.created_at if task.created_at.tzinfo else task.created_at.replace(tzinfo=tz.utc)
    created = created.astimezone(tz.utc)

    assert before <= created <= after, (
        f"created_at {created} outside the [{before}, {after}] window it was created in — "
        f"a timezone-column regression would show up as a multi-hour drift here"
    )
    db.close()

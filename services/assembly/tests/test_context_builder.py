import httpx
from assembly.db import SessionLocal
from assembly.context_builder import store


def test_build_returns_partial_false_when_nothing_relevant_exists(full_stack):
    db = SessionLocal()
    package = store.build(
        db, task_id="task-1", task_description="something with no matching content anywhere zzzznomatch",
        agent_capability="odoo_agent", target_model="qwen-coder", namespace="proj-empty",
    )
    assert package.classification_ceiling == "confidential"  # qwen-coder is local
    assert package.partial is False
    db.close()


def test_build_retrieves_real_vector_search_content(full_stack):
    httpx.post(
        f"{full_stack['knowledge']}/vector/ingest",
        json={"source": "test-doc", "content": "the sale.order model tracks order lifecycle state through approval", "project_id": "proj-ctx-1"},
    )

    db = SessionLocal()
    package = store.build(
        db, task_id="task-2", task_description="explain the sale order lifecycle",
        agent_capability="odoo_agent", target_model="qwen-coder", namespace="proj-ctx-1",
    )
    result = store.get_package(db, package.id)
    _, items = result
    assert any("sale.order" in i.content for i in items)
    db.close()


def test_build_respects_classification_ceiling_for_external_model(full_stack):
    httpx.post(
        f"{full_stack['knowledge']}/vector/ingest",
        json={"source": "secret-doc", "content": "confidential pricing formula unique marker qwxyz", "project_id": "proj-ctx-2", "classification": "confidential"},
    )

    db = SessionLocal()
    # external, unrecognized model -> public ceiling -> should NOT see confidential content
    package = store.build(
        db, task_id="task-3", task_description="pricing formula qwxyz",
        agent_capability="odoo_agent", target_model="some-external-gpt", namespace="proj-ctx-2",
    )
    assert package.classification_ceiling == "public"
    _, items = store.get_package(db, package.id)
    assert not any("pricing formula" in i.content for i in items)
    db.close()


def test_pinned_facts_are_always_included(full_stack):
    db = SessionLocal()
    store.pin_fact(db, namespace="proj-ctx-3", content="ALWAYS REMEMBER: fiscal year starts in April", pinned_by="human_admin")

    package = store.build(
        db, task_id="task-4", task_description="totally unrelated query about docker containers",
        agent_capability="odoo_agent", target_model="qwen-coder", namespace="proj-ctx-3",
    )
    _, items = store.get_package(db, package.id)
    assert any("fiscal year" in i.content for i in items)
    assert any(i.included_reason == "pinned" for i in items)
    db.close()


def test_get_nonexistent_package_returns_none(full_stack):
    db = SessionLocal()
    assert store.get_package(db, "nonexistent-id") is None
    db.close()


def test_build_logs_a_reference_to_the_central_audit_trail(full_stack):
    db = SessionLocal()
    package = store.build(
        db, task_id="task-5", task_description="anything",
        agent_capability="odoo_agent", target_model="qwen-coder", namespace="proj-ctx-5",
    )
    events = httpx.get(f"{full_stack['governance']}/audit/query", params={"actor_id": "context_builder"}).json()
    assert any(e["resource"] == package.id for e in events)
    db.close()

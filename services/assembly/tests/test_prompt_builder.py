import httpx
from assembly.db import SessionLocal
from assembly.prompt_builder import templates as template_store
from assembly.prompt_builder.render import render, NoActiveTemplate, PromptTooLarge

SCHEMA = {
    "reasoning": "str", "answer_or_proposal": "str", "confidence": "float",
    "provenance": "list", "risk_classification": "str", "delegate_to": "optional_str",
}

TEMPLATE_BODY = "You are the Odoo Agent.\n\nTask: {task_description}\n\n{untrusted_warning}\n\nContext:\n{context}\n\n{shared_fragment}"


def _approve_and_reconcile(db, template, governance_url):
    httpx.post(f"{governance_url}/approval/{template.approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    template_store.reconcile_pending(db)


def test_template_registration_requires_real_approval(governance_url):
    db = SessionLocal()
    template, outcome = template_store.register_template(db, "odoo_agent", TEMPLATE_BODY, SCHEMA, created_by="human_admin")
    assert outcome["status"] == "pending_approval"
    assert template_store.get_active_template(db, "odoo_agent") is None  # not active yet

    _approve_and_reconcile(db, template, governance_url)
    active = template_store.get_active_template(db, "odoo_agent")
    assert active is not None
    assert active.id == template.id
    db.close()


def test_rejected_template_never_becomes_active(governance_url):
    db = SessionLocal()
    template, outcome = template_store.register_template(db, "test_agent_reject", TEMPLATE_BODY, SCHEMA, created_by="human_admin")
    httpx.post(f"{governance_url}/approval/{outcome['approval_id']}/decide", json={"decided_by": "human_admin", "approve": False})
    template_store.reconcile_pending(db)
    assert template_store.get_active_template(db, "test_agent_reject") is None
    db.close()


def test_render_wraps_context_in_untrusted_delimiters_and_injects_shared_fragment(governance_url):
    db = SessionLocal()
    template, outcome = template_store.register_template(db, "odoo_agent_render_test", TEMPLATE_BODY, SCHEMA, created_by="human_admin")
    _approve_and_reconcile(db, template, governance_url)

    context_items = [{"content": "the sale.order model tracks state", "provenance": "odoo-docs", "source_type": "vector"}]
    result = render(db, {"id": "ctx-1"}, context_items, "explain sale.order", "odoo_agent_render_test", "qwen-coder")

    assert "<untrusted_context" in result["rendered_prompt"]
    assert "the sale.order model tracks state" in result["rendered_prompt"]
    assert "risk_classification" in result["rendered_prompt"]  # shared fragment's schema description
    assert result["expected_output_schema"] == SCHEMA
    db.close()


def test_render_with_no_active_template_raises():
    db = SessionLocal()
    try:
        render(db, {"id": "ctx-2"}, [], "task", "nonexistent_agent_template", "qwen-coder")
        assert False, "should have raised"
    except NoActiveTemplate:
        pass
    db.close()


def test_rendered_json_schema_example_uses_single_braces_not_doubled(governance_url):
    """
    Regression test: the shared fragment is substituted as a .format()
    VALUE, not used as the format string itself, so {{ }} in it would
    never get unescaped back to single braces — it would render as
    literal double braces, which is not valid JSON and could confuse a
    real model into producing malformed output. Caught via a live
    end-to-end render, not by reading the code.
    """
    db = SessionLocal()
    template, outcome = template_store.register_template(db, "brace_test_agent", TEMPLATE_BODY, SCHEMA, created_by="human_admin")
    _approve_and_reconcile(db, template, governance_url)

    result = render(db, {"id": "ctx-brace"}, [], "task", "brace_test_agent", "qwen-coder")
    assert '{{' not in result["rendered_prompt"]
    assert '"reasoning"' in result["rendered_prompt"]
    assert result["rendered_prompt"].count('"reasoning": "your reasoning, in your own words"') == 1
    db.close()


def test_render_refuses_rather_than_silently_truncates(governance_url):
    db = SessionLocal()
    template, outcome = template_store.register_template(db, "odoo_agent_size_test", TEMPLATE_BODY, SCHEMA, created_by="human_admin")
    _approve_and_reconcile(db, template, governance_url)

    huge_context = [{"content": " ".join(["word"] * 5000), "provenance": "huge-doc", "source_type": "vector"}]
    try:
        render(db, {"id": "ctx-3"}, huge_context, "task", "odoo_agent_size_test", "qwen-coder", max_prompt_words=100)
        assert False, "should have raised"
    except PromptTooLarge:
        pass
    db.close()

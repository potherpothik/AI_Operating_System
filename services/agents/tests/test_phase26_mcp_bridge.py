import json
import uuid
import httpx

from agents.db import SessionLocal
from agents.reasoning_engine import loop, capability_registry
from agents.research_agent import register as research_agent_register

LOCAL_MODEL = "qwen3.5:4b"


def _ensure_ready(register_module, governance_url, assembly_url):
    db = SessionLocal()
    capability_registry.load_all(db)
    db.close()

    result = register_module.ensure_template_registered(created_by="test-suite")
    if result["registered"]:
        approval_id = result["result"]["approval_id"]
        httpx.post(f"{governance_url}/approval/{approval_id}/decide", json={"decided_by": "human_admin", "approve": True})
    httpx.post(f"{assembly_url}/prompt/templates/reconcile-approvals")


def _stub(action, **overrides):
    base = {
        "reasoning": "test reasoning", "answer_or_proposal": "test answer", "confidence": 0.9,
        "provenance": [], "risk_classification": "low", "delegate_to": None, "action": action,
        "mcp_server_name": None, "mcp_tool_name": None, "mcp_params_json": None,
    }
    base.update(overrides)
    return json.dumps(base)


def _register_and_activate_stub_server(governance_url, extensibility_url, stub_mcp_server, name):
    result = httpx.post(
        f"{extensibility_url}/mcp/register",
        json={"name": name, "url": stub_mcp_server, "local_only": True, "registered_by": "human_admin"},
    ).json()
    httpx.post(f"{governance_url}/approval/{result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})
    activated = httpx.post(f"{extensibility_url}/mcp/servers/{result['server_id']}/activate").json()
    assert activated["status"] == "active"
    return activated


# ---------------------------------------------------------------------------
# Phase 26: wiring the existing MCP client (Phase 12) into Reasoning Engine
# as a real tool source for Research Agent — genuinely registers/activates a
# real stub MCP server via extensibility's real endpoints, then confirms
# research_agent's research.invoke_mcp_tool action really dispatches through
# mcp_bridge.py -> clients.mcp_invoke() -> extensibility's real /mcp/invoke
# -> the real stub server, and the real result folds back into the loop.
# ---------------------------------------------------------------------------

def test_research_agent_invokes_a_real_registered_mcp_tool(full_stack, extensibility_url, stub_mcp_server, monkeypatch):
    _ensure_ready(research_agent_register, full_stack["governance"], full_stack["assembly"])

    server_name = f"pytest-research-mcp-{uuid.uuid4().hex[:8]}"
    _register_and_activate_stub_server(full_stack["governance"], extensibility_url, stub_mcp_server, server_name)

    from agents import clients
    monkeypatch.setattr(clients, "EXTENSIBILITY_URL", extensibility_url)

    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub(
                "research.invoke_mcp_tool", mcp_server_name=server_name, mcp_tool_name="echo",
                mcp_params_json=json.dumps({"text": "hello from research agent"}),
            )
        assert "hello from research agent" in prompt
        return _stub("research.invoke_mcp_tool", answer_or_proposal="The tool echoed back the real text.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"research-mcp-test-{uuid.uuid4().hex[:8]}",
        task_description=f"Call the echo tool on {server_name} with text 'hello from research agent'.",
        agent_capability="research_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2
    assert execution.result["answer_or_proposal"] == "The tool echoed back the real text."


def test_research_agent_reports_unknown_server_name_honestly(full_stack, extensibility_url, monkeypatch):
    _ensure_ready(research_agent_register, full_stack["governance"], full_stack["assembly"])

    from agents import clients
    monkeypatch.setattr(clients, "EXTENSIBILITY_URL", extensibility_url)

    calls = {"count": 0}

    def fake_generate(model, prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return _stub("research.invoke_mcp_tool", mcp_server_name="definitely-not-a-real-server", mcp_tool_name="echo", mcp_params_json="{}")
        assert "no active MCP server named" in prompt
        return _stub("research.invoke_mcp_tool", answer_or_proposal="No such server is registered.", risk_classification="informational")

    monkeypatch.setattr(loop, "generate", fake_generate)

    db = SessionLocal()
    execution = loop.execute(
        db, task_id=f"research-mcp-unknown-test-{uuid.uuid4().hex[:8]}",
        task_description="Call a tool on a server that was never registered.",
        agent_capability="research_agent", namespace="default", target_model=LOCAL_MODEL,
    )
    db.close()

    assert execution.status == "completed"
    assert execution.iterations_used == 2

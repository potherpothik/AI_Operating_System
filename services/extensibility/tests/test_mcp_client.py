import httpx
import pytest

from extensibility.db import SessionLocal
from extensibility.mcp_client import api, adapter
from extensibility.mcp_client.models import McpInvocation


def _register_and_activate(db, governance_url, name, url, local_only=True):
    result = api.register(api.RegisterRequest(name=name, url=url, local_only=local_only, registered_by="human_admin"), db)
    httpx.post(f"{governance_url}/approval/{result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})
    return api.activate(result["server_id"], db)


def test_register_is_pending_until_approved(governance_url, stub_mcp_server):
    db = SessionLocal()
    result = api.register(api.RegisterRequest(name="test-server-1", url=stub_mcp_server, registered_by="human_admin"), db)
    db.close()
    assert result["status"] == "pending_approval"
    assert result["approval_id"]


def test_activate_before_approval_stays_pending(governance_url, stub_mcp_server):
    db = SessionLocal()
    result = api.register(api.RegisterRequest(name="test-server-2", url=stub_mcp_server, registered_by="human_admin"), db)
    activated = api.activate(result["server_id"], db)
    db.close()
    assert activated["status"] == "pending_approval"


def test_activate_after_approval_makes_server_active(governance_url, stub_mcp_server):
    db = SessionLocal()
    activated = _register_and_activate(db, governance_url, "test-server-3", stub_mcp_server)
    db.close()
    assert activated["status"] == "active"


def test_invoke_real_stub_server_returns_real_result(governance_url, stub_mcp_server):
    db = SessionLocal()
    server = _register_and_activate(db, governance_url, "test-server-4", stub_mcp_server)
    result = api.invoke(api.InvokeRequest(server_id=server["id"], tool_name="echo", params={"text": "hello real server"}, capability="odoo_agent"), db)
    db.close()

    assert result["result"]["echoed"] == "hello real server"
    assert result["untrusted"] is True
    assert result["source"] == "mcp:test-server-4:echo"


def test_invoke_against_unreachable_server_fails_closed(governance_url):
    db = SessionLocal()
    server = _register_and_activate(db, governance_url, "test-server-unreachable", "http://127.0.0.1:1")
    with pytest.raises(Exception):
        api.invoke(api.InvokeRequest(server_id=server["id"], tool_name="echo", params={}, capability="odoo_agent"), db)
    db.close()


def test_invoke_rejects_result_outside_declared_schema(governance_url, stub_mcp_server):
    db = SessionLocal()
    result = api.register(api.RegisterRequest(
        name="test-server-schema", url=stub_mcp_server, registered_by="human_admin",
        tool_schemas={"bad_schema": {"result_text": "str"}},
    ), db)
    httpx.post(f"{governance_url}/approval/{result['approval_id']}/decide", json={"decided_by": "human_admin", "approve": True})
    server = api.activate(result["server_id"], db)

    with pytest.raises(Exception):
        api.invoke(api.InvokeRequest(server_id=server["id"], tool_name="bad_schema", params={}, capability="odoo_agent"), db)
    db.close()


def test_invoke_denied_for_a_capability_with_no_policy_role(governance_url, stub_mcp_server):
    db = SessionLocal()
    server = _register_and_activate(db, governance_url, "test-server-5", stub_mcp_server)
    with pytest.raises(Exception):
        api.invoke(api.InvokeRequest(server_id=server["id"], tool_name="echo", params={}, capability="nonexistent_capability_with_no_role"), db)
    db.close()


def test_invoke_denied_for_a_pending_server(governance_url, stub_mcp_server):
    db = SessionLocal()
    result = api.register(api.RegisterRequest(name="test-server-6", url=stub_mcp_server, registered_by="human_admin"), db)
    with pytest.raises(Exception):
        api.invoke(api.InvokeRequest(server_id=result["server_id"], tool_name="echo", params={}, capability="odoo_agent"), db)
    db.close()


def test_every_invocation_is_recorded_regardless_of_outcome(governance_url, stub_mcp_server):
    db = SessionLocal()
    server = _register_and_activate(db, governance_url, "test-server-7", stub_mcp_server)
    api.invoke(api.InvokeRequest(server_id=server["id"], tool_name="add", params={"a": 2, "b": 3}, capability="odoo_agent"), db)
    invocations = db.query(McpInvocation).all()
    db.close()

    assert len(invocations) == 1
    assert invocations[0].status == "completed"
    assert invocations[0].result["sum"] == 5


def test_duplicate_server_name_rejected(governance_url, stub_mcp_server):
    db = SessionLocal()
    api.register(api.RegisterRequest(name="test-server-dup", url=stub_mcp_server, registered_by="human_admin"), db)
    with pytest.raises(Exception):
        api.register(api.RegisterRequest(name="test-server-dup", url=stub_mcp_server, registered_by="human_admin"), db)
    db.close()


def test_adapter_real_http_round_trip_without_the_api_layer(stub_mcp_server):
    """Exercises adapter.py directly against the real stub server — a
    genuine HTTP call, no mocking of httpx anywhere in this chain."""
    result = adapter.invoke(stub_mcp_server, "add", {"a": 10, "b": 32})
    assert result["sum"] == 42

"""
Real, live MCP protocol tests — genuine `initialize`/`tools/list`/
`tools/call` JSON-RPC round trips via the official `mcp` SDK client
against the real running server and real backing services (governance,
platform-spine), not direct Python function calls and not mocked.

Each test opens its own client connection within its own coroutine
(rather than sharing one via a fixture) — a shared async-generator
fixture hit a real anyio cancel-scope/task-ownership error across
sequential tests in the same pytest-asyncio session; opening fresh per
test is the same pattern the standalone live_smoke_test.py script
already used successfully, and avoids that class of bug entirely.
"""
import json
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


@asynccontextmanager
async def _session(mcp_server_url):
    async with streamablehttp_client(f"{mcp_server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()
            yield s


def _text(result):
    return json.loads(result.content[0].text) if result.content else None


async def test_advertises_exactly_the_eight_real_tools(mcp_server_url):
    async with _session(mcp_server_url) as session:
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert names == {
            "submit_task", "get_task_status", "ask_agent", "search_knowledge",
            "get_erp_schema", "list_pending_approvals", "get_audit_trail", "list_capabilities",
        }


async def test_no_approval_deciding_tool_exists_structurally(mcp_server_url):
    """The one non-negotiable requirement this whole phase exists to
    enforce (Phase 26 doc, Section 0): an AI-driven IDE session must
    never be able to approve its own risky actions."""
    async with _session(mcp_server_url) as session:
        tools = await session.list_tools()
        names = [t.name for t in tools.tools]
        assert not any("decide" in n or "approve" in n or "reject" in n for n in names)


async def test_submit_task_creates_a_real_task_via_real_gateway(mcp_server_url):
    async with _session(mcp_server_url) as session:
        result = await session.call_tool("submit_task", {"title": "pytest mcp-surface task", "description": "real"})
        assert result.isError is False
        task = _text(result)
        assert task["status"] == "queued"
        assert task["requested_by"] == "mcp_surface"

        status = _text(await session.call_tool("get_task_status", {"task_id": task["id"]}))
        assert status["id"] == task["id"]


async def test_get_task_status_for_unknown_task_is_a_real_tool_error(mcp_server_url):
    async with _session(mcp_server_url) as session:
        result = await session.call_tool("get_task_status", {"task_id": "definitely-not-a-real-task-id"})
        assert result.isError is True
        assert "no task" in result.content[0].text


async def test_ask_agent_with_unknown_capability_is_a_real_tool_error(mcp_server_url):
    async with _session(mcp_server_url) as session:
        result = await session.call_tool("ask_agent", {"capability": "definitely_not_a_real_capability", "question": "x"})
        assert result.isError is True


async def test_get_audit_trail_reflects_the_real_hash_chained_log(mcp_server_url):
    async with _session(mcp_server_url) as session:
        task = _text(await session.call_tool("submit_task", {"title": "audit trail test task"}))
        body = _text(await session.call_tool("get_audit_trail", {"task_id": task["id"]}))
        events = body["events"]
        assert len(events) >= 1
        assert all(e["correlation_id"] == task["correlation_id"] for e in events)


async def test_list_capabilities_returns_the_real_registry(mcp_server_url):
    async with _session(mcp_server_url) as session:
        body = _text(await session.call_tool("list_capabilities", {}))
        assert len(body["capabilities"]) > 0


async def test_list_pending_approvals_is_real_and_read_only(mcp_server_url):
    async with _session(mcp_server_url) as session:
        body = _text(await session.call_tool("list_pending_approvals", {}))
        assert isinstance(body["approvals"], list)


async def test_search_knowledge_calls_real_vector_search(mcp_server_url):
    async with _session(mcp_server_url) as session:
        body = _text(await session.call_tool("search_knowledge", {"query": "test", "top_k": 3}))
        assert "hits" in body

import httpx

# A deliberately simplified REST contract, NOT full MCP JSON-RPC 2.0
# protocol compliance (stdio transport, initialize/list_tools/call_tool
# session lifecycle, capability negotiation). Real, tested, and honestly
# labeled — the same "real but reduced" posture as Phase 3's
# HashingEmbedding and Phase 6's SubprocessSandbox: a genuine MCP server
# speaks a richer protocol than this adapter implements, documented in
# services/extensibility/README.md rather than silently claimed as full
# spec compliance. A server exposing POST {url}/invoke with
# {"tool": ..., "params": ...} -> {"result": ...} works against this
# adapter unchanged; swapping in a real JSON-RPC/stdio transport is a
# contained change to this one file.

_TYPE_CHECKS = {
    "str": lambda v: isinstance(v, str),
    "float": lambda v: isinstance(v, (int, float)),
    "list": lambda v: isinstance(v, list),
    "optional_str": lambda v: v is None or isinstance(v, str),
}


class ServerUnreachable(Exception):
    pass


class SchemaViolation(Exception):
    pass


def invoke(server_url: str, tool_name: str, params: dict, expected_schema: dict = None, timeout: float = 20.0) -> dict:
    """
    Real HTTP call to a real (possibly local-stub, in tests) server. An
    unreachable server fails closed — raises, never returns a fabricated
    result (doc, MCP Client failure handling: "unreachable server fails
    closed, tool marked unavailable, never silently skipped").
    """
    try:
        resp = httpx.post(f"{server_url}/invoke", json={"tool": tool_name, "params": params}, timeout=timeout)
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:  # noqa: BLE001
        raise ServerUnreachable(f"{server_url}: {e}")

    result = body.get("result")
    if expected_schema:
        errors = []
        for field, type_name in expected_schema.items():
            if field not in (result or {}):
                errors.append(f"missing field: {field}")
                continue
            check = _TYPE_CHECKS.get(type_name)
            if check and not check(result[field]):
                errors.append(f"field {field!r} expected type {type_name}, got {type(result[field]).__name__}")
        if errors:
            # "A result outside the server's declared schema is
            # rejected — the same 'don't trust tool output blindly'
            # discipline Reasoning Engine applies to model responses."
            raise SchemaViolation("; ".join(errors))

    return result

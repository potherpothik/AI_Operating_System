import json
import xmlrpc.client
from urllib.parse import urlparse

from agents import clients

# Phase 29: real XML-RPC access against Odoo's own real, documented
# external API (/xmlrpc/2/common for auth, /xmlrpc/2/object for model
# calls) — upgrading odoo.read_orm from cached-schema-only reads
# (Phase 5's own honest scope) to a genuine live-scoped read, when a
# real Odoo instance is actually configured. A NEW action
# (odoo.read_orm_live), not a silent behavior change to odoo.read_orm
# itself — every existing test/caller relying on odoo.read_orm's
# cached-only behavior stays exactly as it was.
TOOL_ACTIONS = {"odoo.read_orm_live"}

_TIMEOUT_SECONDS = 15.0


def _connection_from_url(connection_string: str) -> tuple[str, str, str, str]:
    parsed = urlparse(connection_string)
    url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    db = parsed.path.lstrip("/")
    return url, db, parsed.username or "", parsed.password or ""


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    model = (parsed.get("odoo_model") or "").strip()
    if not model:
        return {"summary": "odoo_model was empty — nothing to query"}

    raw_domain = parsed.get("odoo_domain_json") or "[]"
    raw_fields = parsed.get("odoo_fields_json") or "[]"
    try:
        domain = json.loads(raw_domain)
        fields = json.loads(raw_fields)
    except json.JSONDecodeError as e:
        return {"summary": f"odoo_domain_json/odoo_fields_json was not valid JSON ({e})"}
    if not isinstance(domain, list) or not isinstance(fields, list):
        return {"summary": "odoo_domain_json and odoo_fields_json must both be JSON arrays"}

    secret = clients.resolve_secret("live_odoo", agent_capability, correlation_id=correlation_id or "")
    if not secret["ok"]:
        # Honest, structural finding — no live Odoo instance is configured
        # in this environment, same posture as Phase 22's coding gateway
        # gate reporting a real "unsafe_backend" rather than pretending
        # to have run something it didn't.
        return {"summary": f"no live Odoo connection available: {secret['error']}"}

    try:
        url, db, username, password = _connection_from_url(secret["connection_string"])
    except Exception as e:  # noqa: BLE001
        return {"summary": f"ODOO_CONNECTION_URL is malformed: {e}"}

    try:
        common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", allow_none=True)
        uid = common.authenticate(db, username, password, {})
    except Exception as e:  # noqa: BLE001 — real transport/connection failure, never masked as a fabricated result
        return {"summary": f"Odoo instance at {url!r} unreachable: {e}"}

    if not uid:
        return {"summary": f"Odoo authentication failed for db {db!r} — invalid credentials"}

    try:
        models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", allow_none=True)
        records = models.execute_kw(
            db, uid, password, model, "search_read", [domain], {"fields": fields, "limit": 20},
        )
    except xmlrpc.client.Fault as e:
        return {"summary": f"live Odoo query on {model!r} failed: {e.faultString}"}
    except Exception as e:  # noqa: BLE001
        return {"summary": f"live Odoo query on {model!r} failed: {e}"}

    return {"summary": f"live Odoo query on {model!r} returned {len(records)} real record(s): {json.dumps(records)[:1500]}"}

import json
import os
import uuid
from urllib.parse import urlparse

from agents import clients

# Phase 29: real headless-browser page reads via Playwright
# (services/execution/execution/shell_executor/scripts/browser_action.py),
# run through Shell Executor's sandbox — feeds real browser testing of
# AIOS's own web UI (Control UI, Phase 24). Scoped to Testing Agent only,
# a deliberate decision: Research Agent's own template repeatedly and
# explicitly declares zero external web access as a hard invariant since
# Phase 18 ("this system has no external web-access tool anywhere in its
# history") — this adapter does not change that.
TOOL_ACTIONS = {"testing.browse_internal_page"}

CALC_SCRIPTS_DIR = os.environ.get("CALC_SCRIPTS_DIR")
CALC_WORKING_DIR = os.environ.get("CALC_WORKING_DIR", os.environ.get("PROPOSAL_REPO_PATH", "/tmp/ai_os_sandbox"))

# Structural allowlist, checked BEFORE any browser launch is even
# attempted — never a policy convention layered on afterward. Real AIOS
# services in this environment only ever run on localhost/127.0.0.1;
# anything else is refused without ever reaching Shell Executor at all.
_ALLOWED_HOSTS = {"localhost", "127.0.0.1"}


def _is_internal_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and parsed.hostname in _ALLOWED_HOSTS


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    url = (parsed.get("target_url") or "").strip()
    if not url:
        return {"summary": "target_url was empty — nothing to browse"}

    if not _is_internal_url(url):
        return {
            "summary": f"refused: {url!r} is not a recognized internal AIOS target "
                       f"(only {sorted(_ALLOWED_HOSTS)} hosts are allowed) — no browser was launched",
        }

    if not CALC_SCRIPTS_DIR:
        return {"summary": "CALC_SCRIPTS_DIR not configured — cannot browse a real page"}

    script_path = f"{CALC_SCRIPTS_DIR}/browser_action.py"
    screenshot_path = f"{CALC_WORKING_DIR}/browser-{uuid.uuid4().hex[:8]}.png"
    result = clients.shell_execute(
        command="python3", args=[script_path, url, screenshot_path], working_dir=CALC_WORKING_DIR, capability=agent_capability,
        requesting_agent="reasoning_engine", task_id=task_id, mode="read_only", correlation_id=correlation_id or "",
    )
    if not result.get("ok"):
        return {"summary": f"browser navigation failed: {result.get('error')}"}

    stdout = (result["result"].get("stdout") or "").strip()
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return {"summary": f"browser script produced unparseable output: {stdout[:500]}"}
    if "error" in output:
        return {"summary": f"real browser navigation failed: {output['error']}"}
    return {
        "summary": f"real page loaded — url={output['url']}, status_code={output['status_code']}, "
                   f"title={output['title']!r}, screenshot={output['screenshot_path']}, "
                   f"text: {output['text'][:1500]}",
    }

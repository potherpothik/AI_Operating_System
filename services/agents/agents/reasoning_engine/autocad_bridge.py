import json
import os

from agents import clients

# Phase 17: real DXF structure extraction via dxf_parse.py (ezdxf) run
# through Shell Executor's sandbox — the agent explains from a real
# converted, parsed representation, never a guess about what a drawing
# probably contains.
TOOL_ACTIONS = {"autocad.explain_drawing"}

CALC_SCRIPTS_DIR = os.environ.get("CALC_SCRIPTS_DIR")
CALC_WORKING_DIR = os.environ.get("CALC_WORKING_DIR", os.environ.get("PROPOSAL_REPO_PATH", "/tmp/ai_os_sandbox"))


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    action = parsed.get("action")
    if action != "autocad.explain_drawing":
        return {"summary": f"unrecognized tool action {action!r}"}

    if not CALC_SCRIPTS_DIR:
        return {"summary": "CALC_SCRIPTS_DIR not configured — cannot parse a real drawing"}

    dxf_path = (parsed.get("dxf_path") or "").strip()
    if not dxf_path:
        return {"summary": "dxf_path was empty — nothing to parse"}

    script_path = f"{CALC_SCRIPTS_DIR}/dxf_parse.py"
    result = clients.shell_execute(
        command="python3", args=[script_path, dxf_path], working_dir=CALC_WORKING_DIR, capability=agent_capability,
        requesting_agent="reasoning_engine", task_id=task_id, mode="read_only", correlation_id=correlation_id or "",
    )
    if not result.get("ok"):
        return {"summary": f"dxf parse failed: {result.get('error')}"}

    stdout = (result["result"].get("stdout") or "").strip()
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return {"summary": f"dxf parser produced unparseable output: {stdout[:500]}"}
    if "error" in output:
        return {"summary": f"real DXF parse failed: {output['error']}"}
    return {
        "summary": f"real parsed DXF structure — layers={output['layers']}, "
                   f"entity_counts={output['entity_counts']}, extents={output['extents']}, "
                   f"text_content={output['text_content']}",
    }

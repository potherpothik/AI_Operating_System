import json
import os

from agents import clients

# Phase 17: real, deterministic bin-packing — cutlist_solver.py's actual
# first-fit-decreasing heuristic via Shell Executor's sandbox, never a
# layout the model generated as free text.
TOOL_ACTIONS = {"cutlist.run_optimizer"}

CALC_SCRIPTS_DIR = os.environ.get("CALC_SCRIPTS_DIR")
CALC_WORKING_DIR = os.environ.get("CALC_WORKING_DIR", os.environ.get("PROPOSAL_REPO_PATH", "/tmp/ai_os_sandbox"))


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    action = parsed.get("action")
    if action != "cutlist.run_optimizer":
        return {"summary": f"unrecognized tool action {action!r}"}

    if not CALC_SCRIPTS_DIR:
        return {"summary": "CALC_SCRIPTS_DIR not configured — cannot run a real optimizer"}

    stock_length = (parsed.get("stock_length") or "").strip()
    cut_lengths_json = (parsed.get("cut_lengths_json") or "").strip()
    kerf = (parsed.get("kerf") or "").strip()
    if not stock_length or not cut_lengths_json:
        return {"summary": "stock_length and cut_lengths_json are both required to run the real optimizer"}

    script_path = f"{CALC_SCRIPTS_DIR}/cutlist_solver.py"
    args = [script_path, stock_length, cut_lengths_json]
    if kerf:
        args.append(kerf)

    result = clients.shell_execute(
        command="python3", args=args, working_dir=CALC_WORKING_DIR, capability=agent_capability,
        requesting_agent="reasoning_engine", task_id=task_id, mode="read_only", correlation_id=correlation_id or "",
    )
    if not result.get("ok"):
        return {"summary": f"cutlist solve failed: {result.get('error')}"}

    stdout = (result["result"].get("stdout") or "").strip()
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return {"summary": f"solver produced unparseable output: {stdout[:500]}"}
    if "error" in output:
        return {"summary": f"real solve failed: {output['error']}"}
    return {
        "summary": f"real {output['algorithm']} solve: bins_used={output['bins_used']}, "
                   f"waste_total={output['waste_total']}, bins={output['bins']}",
    }

import json
import os

from agents import clients

# Phase 17: the shared "no model-asserted numbers" principle — a real
# formula, already registered by Costing Agent (Phase 9/14), gets
# evaluated by eval_formula.py's restricted AST evaluator via Shell
# Executor's sandbox, and the REAL number feeds back into context. The
# model never computes the result itself.
TOOL_ACTIONS = {"calc.apply_formula"}

# A real absolute path to shell_executor/scripts/ — same "real local
# path, single-host dev convention" PROPOSAL_REPO_PATH already uses
# (Phase 6). No default: a bridge with it unset reports the tool call as
# not_configured, honestly, rather than guessing a path.
CALC_SCRIPTS_DIR = os.environ.get("CALC_SCRIPTS_DIR")
CALC_WORKING_DIR = os.environ.get("CALC_WORKING_DIR", os.environ.get("PROPOSAL_REPO_PATH", "/tmp/ai_os_sandbox"))


def handle_tool_call(parsed: dict, agent_capability: str, task_id: str, correlation_id: str = None) -> dict:
    action = parsed.get("action")
    if action != "calc.apply_formula":
        return {"summary": f"unrecognized tool action {action!r}"}

    if not CALC_SCRIPTS_DIR:
        return {"summary": "CALC_SCRIPTS_DIR not configured — cannot execute a real formula"}

    formula_name = (parsed.get("formula_name") or "").strip()
    if not formula_name:
        return {"summary": "formula_name was empty — nothing to apply"}

    formula = clients.get_formula_by_name(formula_name)
    if not formula.get("ok"):
        return {"summary": f"could not resolve a real registered formula named {formula_name!r}: {formula.get('error')}"}

    inputs_raw = parsed.get("formula_inputs_json") or "{}"
    try:
        json.loads(inputs_raw)
    except json.JSONDecodeError as e:
        return {"summary": f"formula_inputs_json was not valid JSON ({e})"}

    script_path = f"{CALC_SCRIPTS_DIR}/eval_formula.py"
    result = clients.shell_execute(
        command="python3", args=[script_path, formula["formula_ref"], inputs_raw],
        working_dir=CALC_WORKING_DIR, capability=agent_capability, requesting_agent="reasoning_engine",
        task_id=task_id, mode="read_only", correlation_id=correlation_id or "",
    )
    if not result.get("ok"):
        return {"summary": f"formula execution failed: {result.get('error')}"}

    stdout = (result["result"].get("stdout") or "").strip()
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return {"summary": f"formula script produced unparseable output: {stdout[:500]}"}
    if "error" in output:
        return {"summary": f"real formula {formula_name!r} ({formula['formula_ref']!r}) failed to evaluate: {output['error']}"}
    return {"summary": f"real formula {formula_name!r} ({formula['formula_ref']!r}) evaluated to: {output['result']}"}

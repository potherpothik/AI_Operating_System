from agents import clients


def materialize_propose_formula_change(execution) -> dict:
    """
    Called from resume() after an approved costing.propose_formula_change
    — routes through ERP Knowledge Engine's real formula registration
    (Phase 9), which is itself already approval-gated by Memory
    Manager's business_memory retention policy. This is a genuinely
    second, independent approval gate, not a redundant re-check of the
    same one: Reasoning Engine's own governance approval covers "should
    this agent be allowed to propose a formula change at all," and
    business_memory's covers "should this specific durable business
    record actually be written" — the same two-gate shape Phase 7's
    db.propose_write already has (capability-level approval, then a
    connector-level check before the write itself lands).
    """
    result = execution.result or {}
    formula_result = clients.register_formula(
        name=result.get("formula_name") or "", formula_ref=result.get("formula_ref") or "",
        business_purpose=result.get("answer_or_proposal", ""), defined_by=execution.agent_capability,
        target_namespace=result.get("target_namespace") or "",
    )
    return {"attempted": True, "result": formula_result}

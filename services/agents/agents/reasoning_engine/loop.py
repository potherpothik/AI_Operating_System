from sqlalchemy.orm import Session

from agents import clients
from agents.reasoning_engine import store, capability_registry, execution_bridge, database_bridge, shell_bridge, erp_bridge, planner_bridge
from agents.reasoning_engine.ollama_adapter import generate, OllamaUnavailable
from agents.reasoning_engine.models import ReasoningExecution

# Every propose_* action across all six agents (Phase 10 doc, Section 1:
# "logged identically") that lands as a Git Manager MR — Odoo Agent's own
# odoo.propose_change already proved this path generic (Phase 6); these
# four new agents' propose actions reuse it with zero changes to
# execution_bridge.materialize_propose_change itself. accounting.propose_entry
# (Phase 14) reuses it too — a proposed entry becomes a real reviewable
# document, never a direct ledger write, matching this agent's
# deliberately conservative design (doc: "defers... to a human accountant").
GIT_PROPOSE_ACTIONS = {
    "odoo.propose_change",
    "django.propose_config_change",
    "devops.propose_pipeline_change",
    "devops.propose_infra_change",
    "docker.propose_compose_change",
    "testing.propose_new_test",
    "accounting.propose_entry",
}

# Both migration-shaped propose actions materialize via the same Database
# Connector /db/migrate path (Phase 7) — database_bridge.materialize_propose_migration
# already derives target_platform from the execution's own result, so
# django.propose_migration needed zero changes there either.
DB_MIGRATE_PROPOSE_ACTIONS = {"db.propose_migration", "django.propose_migration"}

# Phase 14: Inventory Agent's two propose actions reuse the SAME
# dry-run-then-write path db.propose_write already established —
# database_bridge.materialize_propose_write derives everything from the
# execution's own tracked dry_run_id/agent_capability, needing zero
# changes to support a second agent using it.
DB_WRITE_PROPOSE_ACTIONS = {"db.propose_write", "inventory.propose_adjustment", "inventory.propose_reorder"}

# Phase 14: the one genuinely new materialization path this batch needed
# — costing.propose_formula_change routes through ERP Knowledge Engine's
# existing business-memory registration (Phase 9), not a new write
# mechanism invented for this agent.
ERP_FORMULA_PROPOSE_ACTIONS = {"costing.propose_formula_change"}


class UnknownCapability(Exception):
    pass


def _decide_routing(parsed: dict, cap_def, task_id: str) -> tuple[str, str]:
    """
    Returns (outcome, detail). outcome is one of:
    allow | deny | require_approval | delegate
    The model's output is untrusted input — every field re-validated
    against the agent's actual permitted capability list before routing
    anywhere (Phase 5 doc, Reasoning Engine security notes).
    """
    delegate_to = parsed.get("delegate_to")
    # Planner has its own decomposition/routing mechanism (task_graph,
    # Phase 8) — delegate_to means "hand this single task to one other
    # capability," an individual agent's redirect mechanism that doesn't
    # apply to a capability whose entire job is deciding how work is
    # routed. Ignored here as defense in depth, not just a prompt
    # instruction: found live that the shared fragment's generic
    # delegate_to guidance is generic enough a model will reasonably
    # apply it to Planner too, which would otherwise discard a
    # perfectly good task_graph in favor of a generic handoff.
    if delegate_to and cap_def.agent_capability != "planner":
        return "delegate", delegate_to

    risk = parsed.get("risk_classification", "high")  # missing/unknown risk defaults to the most restrictive
    if cap_def.agent_capability == "planner":
        # Structural invariant, not a judgment call to trust the model
        # on: producing a task_graph never touches real code, data, or
        # systems — each subtask still goes through its own independent
        # approval gate when it actually executes. A plan that itself
        # required human sign-off before any subtask could even be
        # attempted would make routing slower than asking a human
        # directly, defeating Planner's purpose. Found live: the model
        # reasonably self-assessed risk_classification="low" for a plan
        # touching a sensitive-sounding topic, which routed the ENTIRE
        # plan into require_approval before any subtask ever ran.
        risk = "informational"
    action = parsed.get("action")

    if action:
        precheck = capability_registry.local_precheck(cap_def, action)
        if precheck == "deny":
            return "deny", f"action {action!r} not permitted for {cap_def.agent_capability}"

        gov = clients.authorize(actor=cap_def.agent_capability, action=action, resource=task_id)
        if gov["decision"] == "deny":
            return "deny", gov.get("reason", f"denied by policy for action {action!r}")
        if gov["decision"] == "require_approval" or precheck == "require_approval":
            return "require_approval", action
        if risk != "informational":
            # Action itself is allowed, but the agent's own risk self-assessment
            # is above informational — still routes to a human (Odoo Agent
            # doc: "anything above purely informational routes to Human
            # Approval Layer").
            return "require_approval", action
        return "allow", action

    if risk != "informational":
        return "require_approval", "unspecified_action"
    return "allow", "unspecified_action"


def execute(db: Session, task_id: str, task_description: str, agent_capability: str, namespace: str,
            target_model: str = None, max_iterations: int = None, correlation_id: str = None) -> ReasoningExecution:
    cap_def = capability_registry.get_capability(db, agent_capability)
    if not cap_def:
        raise UnknownCapability(f"no capability_def registered for {agent_capability!r}")

    config = clients.get_reasoning_engine_config()
    if target_model is None:
        target_model = config.get("default_local_model") or "qwen-coder"
    if max_iterations is None:
        try:
            max_iterations = int(config.get("max_iterations", 8))
        except (TypeError, ValueError):
            max_iterations = 8

    execution = store.create_execution(db, task_id, agent_capability, target_model, max_iterations, correlation_id)

    # Planner fails closed if Capability Registry is unreachable — no
    # plan is ever produced against a stale or absent roster, and no
    # model call happens at all (Phase 8 doc, Planner failure handling).
    roster_augmentation = None
    if agent_capability == "planner":
        try:
            roster_augmentation = planner_bridge.augment_task_description(task_description)
        except planner_bridge.CapabilityRegistryUnavailable as e:
            return store.finalize(
                db, execution, "failed", 0,
                failure_reason=f"capability registry unreachable, failing closed: {e}",
                context_id=None,
            )

    context = clients.build_context(task_id, task_description, agent_capability, target_model, namespace)
    context_id = context["id"]
    context_full = clients.get_context(context_id)
    context_items = context_full.get("items", [])

    current_task_description = roster_augmentation or task_description
    iterations_used = 0
    final_status = "failed"
    final_result = None
    failure_reason = "iteration_limit_exceeded"
    approval_id = None
    delegate_task_id = None
    last_dry_run_id = None

    for iteration in range(1, max_iterations + 1):
        iterations_used = iteration
        try:
            rendered = clients.render_prompt(context, context_items, current_task_description, cap_def.template_id, target_model)
        except clients.NoActiveTemplate as e:
            final_status, failure_reason = "failed", f"no active prompt template for {cap_def.template_id!r}: {e}"
            store.log_step(db, execution.id, iteration, None, None, None, "failed:no_template")
            break
        except clients.PromptTooLarge as e:
            final_status, failure_reason = "failed", str(e)
            store.log_step(db, execution.id, iteration, None, None, None, "failed:prompt_too_large")
            break

        try:
            raw_response = generate(target_model, rendered["rendered_prompt"])
        except OllamaUnavailable as e:
            final_status, failure_reason = "failed", str(e)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), None, None, "failed:model_unavailable")
            break

        validation = clients.validate_response(raw_response, rendered["expected_output_schema"])

        if not validation["valid"]:
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, None, "invalid_schema:retry")
            errors = "; ".join(validation.get("errors", []))
            # Built from current_task_description, not the original
            # task_description parameter — otherwise a schema-invalid
            # response one iteration after a successful tool call (Phase
            # 7's db.read/db.dry_run) would silently discard the real
            # tool result already folded into current_task_description,
            # and the model would lose the data it was supposed to be
            # reasoning from on its retry.
            current_task_description = (
                f"{current_task_description}\n\n[Your previous response failed validation: {errors}. "
                f"Respond again with ONLY a single JSON object matching the required schema.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", f"schema_invalid_output: {errors}"
            continue

        parsed = validation["parsed"]
        action = parsed.get("action")
        has_fresh_query = bool((parsed.get("sql_template") or "").strip())
        has_fresh_shell_command = bool((parsed.get("shell_command") or "").strip())

        if action in database_bridge.TOOL_ACTIONS and has_fresh_query:
            tool_result = database_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            if action == "db.dry_run" and tool_result.get("dry_run_id"):
                last_dry_run_id = tool_result["dry_run_id"]
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this — if this was a db.read, set action to db.read "
                f"again but leave sql_template empty since you already have the data; if this was a db.dry_run, switch "
                f"action to db.propose_write with the SAME sql_template/params_json plus impact_estimate and risk_classification.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in shell_bridge.TOOL_ACTIONS and has_fresh_shell_command:
            tool_result = shell_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this — set action to {action} again but leave "
                f"shell_command empty since you already have the result, unless you genuinely need to run something else.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if last_dry_run_id:
            # System-tracked, never model-supplied — carried onto whatever
            # gets finalized so resume() can execute the matching write
            # without trusting the model to echo an ID back correctly.
            parsed["dry_run_id"] = last_dry_run_id

        outcome, detail = _decide_routing(parsed, cap_def, task_id)
        clients.audit_log(
            actor_id=agent_capability, action=f"reasoning.{outcome}", resource=task_id,
            decision=outcome, reason=detail, correlation_id=correlation_id or "",
        )

        if outcome == "deny":
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, "refused:policy_denied")
            final_status, final_result = "refused", {**parsed, "denial_reason": detail}
            break

        if outcome == "delegate":
            task = clients.create_delegate_task(
                title=f"delegated from {agent_capability}: {task_id}",
                description=f"needs_agent({detail}): {task_description}",
                correlation_id=correlation_id or "",
            )
            delegate_task_id = task.get("id")
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"delegated:{detail}")
            final_status, final_result = "awaiting_delegation", parsed
            break

        if outcome == "require_approval":
            approval = clients.request_approval(
                action=detail, requested_by=agent_capability,
                risk_tier=parsed.get("risk_classification", "medium"),
                payload_ref=parsed.get("answer_or_proposal", "")[:500],
            )
            approval_id = approval.get("id")
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, "awaiting_approval")
            final_status, final_result = "awaiting_approval", parsed
            break

        # allow
        store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, "completed")
        final_status, final_result = "completed", parsed
        break

    return store.finalize(
        db, execution, final_status, iterations_used, result=final_result,
        approval_id=approval_id, delegate_task_id=delegate_task_id,
        failure_reason=failure_reason if final_status == "failed" else None,
        context_id=context_id,
    )


def resume(db: Session, execution_id: str) -> ReasoningExecution | None:
    execution = store.get_execution(db, execution_id)
    if not execution:
        return None
    if execution.status != "awaiting_approval":
        return execution  # nothing to resume

    approval = clients.get_approval_status(execution.approval_id)
    if approval.get("status") == "approved":
        result = dict(execution.result or {})
        # Phase 6 doc, Section 3: after approval, a propose_* action
        # actually gets materialized as a branch/commit/push/MR (or a real
        # migration file) — not just marked "completed" and left as text.
        # Any other action (or unconfigured execution layer) still just
        # completes as before. Phase 10 doc, Section 1: every new agent's
        # propose_* action reuses these same two bridges unchanged.
        action = result.get("action")
        if action in GIT_PROPOSE_ACTIONS:
            result["git_execution"] = execution_bridge.materialize_propose_change(execution)
        elif action in DB_WRITE_PROPOSE_ACTIONS:
            result["db_execution"] = database_bridge.materialize_propose_write(execution)
        elif action in DB_MIGRATE_PROPOSE_ACTIONS:
            result["db_execution"] = database_bridge.materialize_propose_migration(execution)
        elif action in ERP_FORMULA_PROPOSE_ACTIONS:
            result["erp_execution"] = erp_bridge.materialize_propose_formula_change(execution)
        return store.finalize(
            db, execution, "completed", execution.iterations_used, result=result,
            approval_id=execution.approval_id,
        )
    if approval.get("status") in ("rejected", "expired"):
        return store.finalize(
            db, execution, "rejected", execution.iterations_used, result=execution.result,
            approval_id=execution.approval_id, failure_reason=f"approval {approval.get('status')}",
        )
    return execution  # still pending

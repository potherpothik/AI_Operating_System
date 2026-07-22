from sqlalchemy.orm import Session

from agents import clients
from agents.reasoning_engine import store, capability_registry, execution_bridge, database_bridge, shell_bridge, erp_bridge, planner_bridge, task_bridge, review_bridge, reverse_eng_bridge, calc_bridge, cutlist_bridge, autocad_bridge, security_bridge, coding_gateway_bridge, model_router, mcp_bridge, odoo_live_bridge, django_bridge, browser_bridge
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
    # Phase 15: all four of this batch's propose actions reuse
    # execution_bridge.materialize_propose_change() completely
    # unchanged — every one of them is a plain-language proposal
    # document, the same shape odoo.propose_change already established.
    "manufacturing.propose_schedule_change",
    "sales.propose_quote",
    "sales.propose_order_change",
    "pm.propose_milestone_update",
    # Phase 16: both reuse the same git-proposal path unchanged too —
    # architecture.propose_decision needs nothing further; reverse_eng's
    # own draft gets a SECOND, chained step (REVERSE_ENG_PROPOSE_ACTIONS
    # below) once the git half lands.
    "reverse_eng.propose_documentation_draft",
    "architecture.propose_decision",
    # Phase 17: AutoCAD Agent's proposed annotation reuses the same
    # git-proposal path unchanged too — a plain-language document for a
    # human to review, same as every other propose_* action.
    "autocad.propose_annotation",
    # Phase 18: Python Agent's propose_change, Documentation Agent's
    # propose_new_doc, and Research Agent's propose_external_lookup all
    # reuse the same git-proposal path unchanged too. docs.propose_new_doc
    # gets a SECOND, chained step (REVERSE_ENG_PROPOSE_ACTIONS below),
    # same as reverse_eng's own draft — an approved new doc becomes real
    # Documentation Engine content, not just a committed file.
    "python.propose_change",
    "docs.propose_new_doc",
    "research.propose_external_lookup",
}

# Phase 16: the one action whose git materialization needs a chained
# follow-up — once the draft is a real committed file, reverse_eng_bridge
# ingests that SAME file into Documentation Engine, closing the loop from
# inference to record. Phase 18: Documentation Agent's own propose_new_doc
# reuses this exact bridge unchanged for a second agent — proof it was
# built generically the first time.
REVERSE_ENG_PROPOSE_ACTIONS = {"reverse_eng.propose_documentation_draft", "docs.propose_new_doc"}

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

# Phase 22: the one action whose materialization is a real external CLI
# invocation (Claude Code or OpenCode) rather than a text-file commit —
# coding_gateway_bridge.materialize_propose_run enforces its own
# sandbox-backend safety gate before touching anything (see that
# module's own docstring).
CODING_GATEWAY_PROPOSE_ACTIONS = {"coding_gateway.propose_run"}


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
        # Phase 23: resolve against what's actually pulled in Ollama
        # right now, trying default_local_model then fallback_local_model
        # in priority order — real config keys since Phase 2, never
        # actually checked against reality before this phase.
        try:
            target_model = model_router.resolve_model(config)
        except model_router.AllCandidatesExhausted:
            # Neither configured model is actually available — fall
            # through to the same value this code always defaulted to
            # and let the existing OllamaUnavailable handling below
            # report it for real, rather than inventing a model name.
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
        has_fresh_task_lookup = bool((parsed.get("target_task_id") or "").strip())
        has_fresh_review_request = bool((parsed.get("target_repo") or "").strip())
        has_fresh_formula_request = bool((parsed.get("formula_name") or "").strip())
        has_fresh_cutlist_request = bool((parsed.get("stock_length") or "").strip())
        has_fresh_dxf_request = bool((parsed.get("dxf_path") or "").strip())
        has_fresh_audit_query = bool(
            (parsed.get("audit_correlation_id") or "").strip()
            or (parsed.get("audit_actor_id") or "").strip()
            or (parsed.get("audit_action") or "").strip()
        )
        has_fresh_mcp_request = bool((parsed.get("mcp_tool_name") or "").strip())
        has_fresh_odoo_live_request = bool((parsed.get("odoo_model") or "").strip())
        has_fresh_django_request = bool((parsed.get("manage_py_command") or "").strip())
        has_fresh_browse_request = bool((parsed.get("target_url") or "").strip())

        if action in database_bridge.TOOL_ACTIONS and has_fresh_query:
            tool_result = database_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id, requester_ceiling=cap_def.classification_ceiling)
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

        if action in task_bridge.TOOL_ACTIONS and has_fresh_task_lookup:
            tool_result = task_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this — set action to {action} again but leave "
                f"target_task_id empty since you already have the data, unless you genuinely need to look up a different task.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in review_bridge.TOOL_ACTIONS and has_fresh_review_request:
            tool_result = review_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this — set action to {action} again but leave "
                f"target_repo empty since you already have the result, unless you genuinely need to check something else, "
                f"or set action to review.flag_concern/review.approve_recommendation to finalize.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in calc_bridge.TOOL_ACTIONS and has_fresh_formula_request:
            tool_result = calc_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this real number — set action to {action} again "
                f"but leave formula_name empty since you already have the real result, unless you genuinely need a "
                f"different formula. Never state a different number than the one you were actually given.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in cutlist_bridge.TOOL_ACTIONS and has_fresh_cutlist_request:
            tool_result = cutlist_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this real solver result — set action to {action} "
                f"again but leave stock_length empty since you already have the real result, unless you genuinely need "
                f"a different solve. This finalizing turn requires human approval before the result is treated as final.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in autocad_bridge.TOOL_ACTIONS and has_fresh_dxf_request:
            tool_result = autocad_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this real parsed structure — set action to "
                f"{action} again but leave dxf_path empty since you already have the real result, unless you genuinely "
                f"need to parse a different file.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in security_bridge.TOOL_ACTIONS and has_fresh_audit_query:
            tool_result = security_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this real audit trail — set action to {action} "
                f"again but leave audit_correlation_id/audit_actor_id/audit_action all empty since you already have "
                f"the real result, unless you genuinely need a different query.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in mcp_bridge.TOOL_ACTIONS and has_fresh_mcp_request:
            tool_result = mcp_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this real result — set action to {action} again "
                f"but leave mcp_tool_name empty since you already have the result, unless you genuinely need to call "
                f"another tool.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in odoo_live_bridge.TOOL_ACTIONS and has_fresh_odoo_live_request:
            tool_result = odoo_live_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this real result — set action to {action} again "
                f"but leave odoo_model empty since you already have the result, unless you genuinely need a different "
                f"live query.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in django_bridge.TOOL_ACTIONS and has_fresh_django_request:
            tool_result = django_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this real result — set action to {action} again "
                f"but leave manage_py_command empty since you already have the result, unless you genuinely need to run "
                f"a different check.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", "iteration_limit_exceeded_during_tool_call"
            continue

        if action in browser_bridge.TOOL_ACTIONS and has_fresh_browse_request:
            tool_result = browser_bridge.handle_tool_call(parsed, agent_capability, task_id, correlation_id)
            store.log_step(db, execution.id, iteration, rendered.get("render_log_id"), raw_response, parsed, f"tool_call:{action}")
            current_task_description = (
                f"{current_task_description}\n\n[System: result of your {action} request — {tool_result['summary']}. "
                f"Now produce your final structured response based on this real page content — set action to {action} "
                f"again but leave target_url empty since you already have the result, unless you genuinely need to "
                f"browse a different internal page.]"
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
        if action in review_bridge.REVIEW_ATTACH_ACTIONS:
            # Code Review Agent's own actions never require approval —
            # attach synchronously here, no resume() step needed, since
            # there's no approval gate on ITS output (Phase 16 doc,
            # Section 1). materialize_attach_review only reads
            # execution.result/.agent_capability/.id, so setting result
            # in memory (no commit yet — the real finalize() call below
            # does that, with review_execution already folded in) is
            # sufficient.
            execution.result = parsed
            parsed = dict(parsed)
            parsed["review_execution"] = review_bridge.materialize_attach_review(execution)
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
            if action in REVERSE_ENG_PROPOSE_ACTIONS:
                result["docs_execution"] = reverse_eng_bridge.materialize_propose_documentation(execution, result["git_execution"])
        elif action in DB_WRITE_PROPOSE_ACTIONS:
            result["db_execution"] = database_bridge.materialize_propose_write(execution)
        elif action in DB_MIGRATE_PROPOSE_ACTIONS:
            result["db_execution"] = database_bridge.materialize_propose_migration(execution)
        elif action in ERP_FORMULA_PROPOSE_ACTIONS:
            result["erp_execution"] = erp_bridge.materialize_propose_formula_change(execution)
        elif action in CODING_GATEWAY_PROPOSE_ACTIONS:
            result["coding_gateway_execution"] = coding_gateway_bridge.materialize_propose_run(execution)
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

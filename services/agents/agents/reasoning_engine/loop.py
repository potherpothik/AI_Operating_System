from sqlalchemy.orm import Session

from agents import clients
from agents.reasoning_engine import store, capability_registry
from agents.reasoning_engine.ollama_adapter import generate, OllamaUnavailable
from agents.reasoning_engine.models import ReasoningExecution


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
    if delegate_to:
        return "delegate", delegate_to

    risk = parsed.get("risk_classification", "high")  # missing/unknown risk defaults to the most restrictive
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

    context = clients.build_context(task_id, task_description, agent_capability, target_model, namespace)
    context_id = context["id"]
    context_full = clients.get_context(context_id)
    context_items = context_full.get("items", [])

    current_task_description = task_description
    iterations_used = 0
    final_status = "failed"
    final_result = None
    failure_reason = "iteration_limit_exceeded"
    approval_id = None
    delegate_task_id = None

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
            current_task_description = (
                f"{task_description}\n\n[Your previous response failed validation: {errors}. "
                f"Respond again with ONLY a single JSON object matching the required schema.]"
            )
            if iteration == max_iterations:
                final_status, failure_reason = "failed", f"schema_invalid_output: {errors}"
            continue

        parsed = validation["parsed"]
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
        return store.finalize(
            db, execution, "completed", execution.iterations_used, result=execution.result,
            approval_id=execution.approval_id,
        )
    if approval.get("status") in ("rejected", "expired"):
        return store.finalize(
            db, execution, "rejected", execution.iterations_used, result=execution.result,
            approval_id=execution.approval_id, failure_reason=f"approval {approval.get('status')}",
        )
    return execution  # still pending

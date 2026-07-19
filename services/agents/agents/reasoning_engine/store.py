import datetime
from sqlalchemy.orm import Session

from agents.reasoning_engine.models import ReasoningExecution, ReasoningStep


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def create_execution(db: Session, task_id: str, agent_capability: str, target_model: str, max_iterations: int, correlation_id: str = None) -> ReasoningExecution:
    execution = ReasoningExecution(
        task_id=task_id,
        agent_capability=agent_capability,
        target_model=target_model,
        status="in_progress",
        max_iterations=max_iterations,
        correlation_id=correlation_id,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def log_step(db: Session, execution_id: str, iteration: int, prompt_ref: str, raw_response: str, parsed_decision: dict, routing_outcome: str) -> ReasoningStep:
    step = ReasoningStep(
        execution_id=execution_id,
        iteration=iteration,
        prompt_ref=prompt_ref,
        raw_response=raw_response,
        parsed_decision=parsed_decision,
        routing_outcome=routing_outcome,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def finalize(db: Session, execution: ReasoningExecution, status: str, iterations_used: int, result: dict = None,
             approval_id: str = None, delegate_task_id: str = None, failure_reason: str = None, context_id: str = None) -> ReasoningExecution:
    execution.status = status
    execution.iterations_used = iterations_used
    execution.result = result
    execution.approval_id = approval_id
    execution.delegate_task_id = delegate_task_id
    execution.failure_reason = failure_reason
    if context_id is not None:
        execution.context_id = context_id
    terminal = {"completed", "refused", "rejected", "failed"}
    if status in terminal:
        execution.completed_at = _now()
    db.commit()
    db.refresh(execution)
    return execution


def get_execution(db: Session, execution_id: str) -> ReasoningExecution | None:
    return db.query(ReasoningExecution).filter(ReasoningExecution.id == execution_id).first()


def get_steps(db: Session, execution_id: str) -> list[ReasoningStep]:
    return db.query(ReasoningStep).filter(ReasoningStep.execution_id == execution_id).order_by(ReasoningStep.iteration.asc()).all()

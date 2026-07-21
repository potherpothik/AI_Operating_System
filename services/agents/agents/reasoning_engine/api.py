import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agents import clients
from agents.db import get_db
from agents.reasoning_engine import loop, store, model_router, ollama_adapter

router = APIRouter(prefix="/reasoning", tags=["reasoning"])


class ExecuteRequest(BaseModel):
    task_id: str
    task_description: str
    agent_capability: str
    namespace: str = "default"
    # Explicit Optional[...] rather than bare "str = None" — in Pydantic
    # v2, "str = None" only sets the default, it does NOT widen the type
    # to accept an explicit `null` in the request body. Found live: a
    # caller that sends target_model: null (rather than omitting the
    # field entirely) got a 422 even though the field is meant to be
    # optional. Any caller relying on omission alone worked by accident.
    target_model: Optional[str] = None
    max_iterations: Optional[int] = None
    correlation_id: Optional[str] = None


def _execution_out(execution) -> dict:
    return {
        "id": execution.id,
        "task_id": execution.task_id,
        "context_id": execution.context_id,
        "agent_capability": execution.agent_capability,
        "target_model": execution.target_model,
        "status": execution.status,
        "result": execution.result,
        "approval_id": execution.approval_id,
        "delegate_task_id": execution.delegate_task_id,
        "failure_reason": execution.failure_reason,
        "iterations_used": execution.iterations_used,
        "max_iterations": execution.max_iterations,
        "created_at": execution.created_at.isoformat(),
        "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
    }


@router.post("/execute")
def execute(req: ExecuteRequest, db: Session = Depends(get_db)):
    try:
        execution = loop.execute(
            db, req.task_id, req.task_description, req.agent_capability, req.namespace,
            target_model=req.target_model, max_iterations=req.max_iterations, correlation_id=req.correlation_id,
        )
    except loop.UnknownCapability as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _execution_out(execution)


@router.get("/executions")
def list_executions(status: str = None, agent_capability: str = None, db: Session = Depends(get_db)):
    """
    Phase 13: no listing endpoint existed before this — only
    single-execution lookup by id. Metrics Dashboard needs iteration
    counts across many executions; Health Monitor needs to find
    executions genuinely stuck past their own `max_iterations` (status
    still `awaiting_approval`/`in_progress`-shaped after using every
    allotted turn is the honest signal — there's no separate "stuck"
    status of its own).
    """
    executions = store.list_executions(db, status=status, agent_capability=agent_capability)
    return [_execution_out(e) for e in executions]


@router.get("/{execution_id}/trace")
def trace(execution_id: str, db: Session = Depends(get_db)):
    execution = store.get_execution(db, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="execution not found")
    steps = store.get_steps(db, execution_id)
    return {
        "execution": _execution_out(execution),
        "steps": [
            {
                "iteration": s.iteration,
                "prompt_ref": s.prompt_ref,
                "raw_response": s.raw_response,
                "parsed_decision": s.parsed_decision,
                "routing_outcome": s.routing_outcome,
                "ts": s.ts.isoformat(),
            }
            for s in steps
        ],
    }


@router.post("/{execution_id}/resume")
def resume(execution_id: str, db: Session = Depends(get_db)):
    execution = loop.resume(db, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="execution not found")
    return _execution_out(execution)


# ---------------------------------------------------------------------------
# Phase 27: raw model access for the OpenAI-compatible shim
# (services/platform-spine's /v1/chat/completions). Deliberately NOT the
# agentic loop above — no capability boundary, no template, no
# approval gate. This is model_router/ollama_adapter exposed directly
# over HTTP, the minimum a "select AIOS as your IDE's model provider"
# shim needs. Classification-vs-model-ceiling gating happens in the
# CALLER (platform-spine, which owns auth and already calls governance +
# assembly for exactly this) — this endpoint only resolves a real,
# available model and genuinely calls it, nothing more.
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class RawGenerateRequest(BaseModel):
    messages: list[ChatMessage]
    model: Optional[str] = None


@router.get("/available_models")
def available_models():
    """Real, currently-pulled Ollama tags, plus whichever one
    model_router.resolve_model() would actually pick as the default
    right now — never a hardcoded list."""
    provider = model_router.OllamaProvider()
    models = provider.list_models()
    config = clients.get_reasoning_engine_config()
    try:
        default = model_router.resolve_model(config, provider)
    except model_router.AllCandidatesExhausted:
        default = None
    return {"models": models, "default": default}


def _resolve_target_model(model: Optional[str]) -> str:
    provider = model_router.OllamaProvider()
    if model:
        if not provider.has_model(model):
            raise HTTPException(status_code=404, detail=f"model {model!r} is not available on this Ollama instance")
        return model
    config = clients.get_reasoning_engine_config()
    try:
        return model_router.resolve_model(config, provider)
    except model_router.AllCandidatesExhausted as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/raw_generate")
def raw_generate(req: RawGenerateRequest):
    target_model = _resolve_target_model(req.model)
    try:
        result = ollama_adapter.chat(target_model, [m.model_dump() for m in req.messages])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"model call failed: {e}")
    message = result.get("message", {})
    return {
        "model": target_model,
        "content": message.get("content", ""),
        "prompt_eval_count": result.get("prompt_eval_count", 0),
        "eval_count": result.get("eval_count", 0),
    }


@router.post("/raw_generate_stream")
def raw_generate_stream(req: RawGenerateRequest):
    target_model = _resolve_target_model(req.model)

    def event_stream():
        try:
            for chunk in ollama_adapter.chat_stream(target_model, [m.model_dump() for m in req.messages]):
                message = chunk.get("message", {})
                delta = message.get("content", "")
                done = chunk.get("done", False)
                payload = {"delta": delta, "done": done}
                if done:
                    payload["prompt_eval_count"] = chunk.get("prompt_eval_count", 0)
                    payload["eval_count"] = chunk.get("eval_count", 0)
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

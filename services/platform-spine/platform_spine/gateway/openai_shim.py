"""
Phase 27 — OpenAI-Compatible Endpoint. The "GPU-day switch": once a real
GPU server exists, any IDE that already speaks the OpenAI chat-completions
shape (Continue, Cursor, OpenCode) can point at AIOS instead of a vendor's
cloud, and confidential code then flows through AIOS's own classification
and routing instead of leaving the network. A thin translator, not a
second model layer of its own: the real model call happens in
services/agents/ (model_router.py, Phase 23), the real classification
call happens in services/governance/ (Phase 1), and the real
classification-ceiling check happens in services/assembly/ (Phase 4/11).
This module's only job is auth, gating, and shape translation.

Structural bar, not a policy suggestion: a request whose classified
content exceeds the resolved model's ceiling never reaches the model at
all — checked BEFORE the call to services/agents/, not after, and every
decision (allow or deny) is written to the real, hash-chained audit trail.
"""
import json
import os
import time
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from platform_spine.gateway.auth import resolve_actor
from platform_spine.gateway.rate_limit import check_rate_limit
from platform_spine.security_client import authorize, classify, audit_log

AGENTS_URL = os.environ.get("AGENTS_URL", "http://localhost:8005")
ASSEMBLY_URL = os.environ.get("ASSEMBLY_URL", "http://localhost:8004")

router = APIRouter(prefix="/v1", tags=["openai-shim"])

_TIERS = ["public", "internal", "confidential"]


def _tier_index(tier: str) -> int:
    return _TIERS.index(tier) if tier in _TIERS else len(_TIERS) - 1  # unknown tier fails toward most restrictive


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: list[ChatMessage]
    stream: bool = False


def _resolve_default_model() -> Optional[str]:
    resp = httpx.get(f"{AGENTS_URL}/reasoning/available_models", timeout=10.0)
    resp.raise_for_status()
    return resp.json().get("default")


def _ceiling_for_model(target_model: str) -> dict:
    resp = httpx.get(f"{ASSEMBLY_URL}/context/model-ceiling", params={"target_model": target_model}, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def _gate_and_resolve_model(actor: str, correlation_id: str, req: ChatCompletionRequest) -> str:
    """
    Real, structural pre-check: resolve the real candidate model, classify
    the real request content, compare against that model's real ceiling
    (assembly's ceiling_for_model — the same mechanism Code Analysis
    Engine's raw_source_gate.py already relies on, Phase 11), and refuse
    BEFORE ever calling the model if the content outranks it. Every
    outcome is audit-logged, allow or deny.
    """
    target_model = req.model or _resolve_default_model()
    if not target_model:
        raise HTTPException(status_code=503, detail="no local model is currently available")

    combined_content = "\n".join(m.content for m in req.messages)
    classification = classify(combined_content)["classification"]
    ceiling = _ceiling_for_model(target_model)["ceiling"]

    if _tier_index(classification) > _tier_index(ceiling):
        reason = f"content classified {classification!r} exceeds {target_model!r}'s ceiling {ceiling!r}"
        audit_log(actor, "model.generate", target_model, decision="deny", reason=reason, correlation_id=correlation_id)
        raise HTTPException(status_code=403, detail=reason)

    audit_log(
        actor, "model.generate", target_model, decision="allow",
        reason=f"classification={classification!r} ceiling={ceiling!r}", correlation_id=correlation_id,
    )
    return target_model


@router.get("/models")
def list_models(actor: str = Depends(resolve_actor)):
    check_rate_limit(actor)
    correlation_id = str(uuid.uuid4())
    decision = authorize(actor=actor, action="model.list", resource="*", correlation_id=correlation_id)
    if decision["decision"] == "deny":
        raise HTTPException(status_code=403, detail=decision["reason"])

    resp = httpx.get(f"{AGENTS_URL}/reasoning/available_models", timeout=10.0)
    resp.raise_for_status()
    models = resp.json().get("models", [])
    return {
        "object": "list",
        "data": [{"id": m, "object": "model", "created": 0, "owned_by": "aios-local"} for m in models],
    }


@router.post("/chat/completions")
def chat_completions(req: ChatCompletionRequest, actor: str = Depends(resolve_actor)):
    check_rate_limit(actor)
    correlation_id = str(uuid.uuid4())

    decision = authorize(actor=actor, action="model.generate", resource="*", correlation_id=correlation_id)
    if decision["decision"] == "deny":
        raise HTTPException(status_code=403, detail=decision["reason"])

    target_model = _gate_and_resolve_model(actor, correlation_id, req)
    messages = [m.model_dump() for m in req.messages]
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())

    if req.stream:
        def event_stream():
            with httpx.stream(
                "POST", f"{AGENTS_URL}/reasoning/raw_generate_stream",
                json={"model": target_model, "messages": messages}, timeout=120.0,
            ) as resp:
                for line in resp.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    chunk = json.loads(line[len("data: "):])
                    if chunk.get("error"):
                        yield f"data: {json.dumps({'error': chunk['error']})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    if chunk.get("done"):
                        final = {
                            "id": completion_id, "object": "chat.completion.chunk", "created": created,
                            "model": target_model, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        }
                        yield f"data: {json.dumps(final)}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                    piece = {
                        "id": completion_id, "object": "chat.completion.chunk", "created": created,
                        "model": target_model,
                        "choices": [{"index": 0, "delta": {"content": chunk.get("delta", "")}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(piece)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    resp = httpx.post(
        f"{AGENTS_URL}/reasoning/raw_generate", json={"model": target_model, "messages": messages}, timeout=120.0,
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"agents service returned {resp.status_code}: {resp.text}")
    body = resp.json()
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": target_model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": body["content"]}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": body.get("prompt_eval_count", 0),
            "completion_tokens": body.get("eval_count", 0),
            "total_tokens": body.get("prompt_eval_count", 0) + body.get("eval_count", 0),
        },
    }

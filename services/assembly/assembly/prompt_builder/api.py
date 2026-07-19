from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from assembly.db import get_db
from assembly.prompt_builder import templates as template_store
from assembly.prompt_builder.render import render, NoActiveTemplate, PromptTooLarge
from assembly.prompt_builder.schema_validate import validate_response

router = APIRouter(prefix="/prompt", tags=["prompt"])


class TemplateRegister(BaseModel):
    agent_template_id: str
    body: str
    expected_output_schema: dict
    created_by: str


class RenderRequest(BaseModel):
    context_package: dict
    context_items: list
    task_description: str
    agent_template_id: str
    target_model: str
    max_prompt_words: int = 4000


class ValidateRequest(BaseModel):
    raw_response: str
    expected_output_schema: dict


@router.post("/templates")
def register_template(req: TemplateRegister, db: Session = Depends(get_db)):
    template, outcome = template_store.register_template(db, req.agent_template_id, req.body, req.expected_output_schema, req.created_by)
    return {"id": template.id, "agent_template_id": template.agent_template_id, "version": template.version, **outcome}


@router.get("/templates")
def list_templates(db: Session = Depends(get_db)):
    rows = template_store.list_templates(db)
    return [{"id": t.id, "agent_template_id": t.agent_template_id, "version": t.version, "status": t.status} for t in rows]


@router.post("/templates/reconcile-approvals")
def reconcile(db: Session = Depends(get_db)):
    updated = template_store.reconcile_pending(db)
    return {"updated": [{"id": t.id, "status": t.status} for t in updated]}


@router.post("/render")
def render_prompt(req: RenderRequest, db: Session = Depends(get_db)):
    try:
        result = render(db, req.context_package, req.context_items, req.task_description, req.agent_template_id, req.target_model, req.max_prompt_words)
    except NoActiveTemplate as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PromptTooLarge as e:
        raise HTTPException(status_code=413, detail=str(e))
    return result


@router.post("/validate-response")
def validate(req: ValidateRequest):
    return validate_response(req.raw_response, req.expected_output_schema)

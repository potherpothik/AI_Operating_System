import json
from sqlalchemy.orm import Session

from assembly.prompt_builder.models import PromptTemplate
from assembly.clients import request_approval, get_approval_status


def register_template(db: Session, agent_template_id: str, body: str, expected_output_schema: dict, created_by: str) -> tuple[PromptTemplate, dict]:
    """
    New templates and version changes require approval — a malicious or
    buggy template is a real channel for weakening the refuse/delegate/
    approval instructions baked into every agent (Phase 4 design doc).
    """
    existing = (
        db.query(PromptTemplate)
        .filter(PromptTemplate.agent_template_id == agent_template_id, PromptTemplate.status == "active")
        .order_by(PromptTemplate.created_at.desc())
        .first()
    )
    next_version = str(int(existing.version) + 1) if existing and existing.version.isdigit() else "1"

    approval = request_approval(
        action=f"prompt_template.register.{agent_template_id}", requested_by=created_by, risk_tier="medium", payload_ref=agent_template_id
    )

    template = PromptTemplate(
        agent_template_id=agent_template_id,
        version=next_version,
        body=body,
        expected_output_schema=json.dumps(expected_output_schema),
        status="pending_approval" if approval.get("id") else "rejected",
        approval_id=approval.get("id"),
        created_by=created_by,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template, {"status": template.status, "approval_id": approval.get("id")}


def reconcile_pending(db: Session) -> list[PromptTemplate]:
    updated = []
    for template in db.query(PromptTemplate).filter(PromptTemplate.status == "pending_approval").all():
        if not template.approval_id:
            continue
        result = get_approval_status(template.approval_id)
        if result.get("status") == "approved":
            template.status = "active"
            updated.append(template)
        elif result.get("status") in ("rejected", "expired"):
            template.status = "rejected"
            updated.append(template)
    db.commit()
    return updated


def get_active_template(db: Session, agent_template_id: str):
    # created_at, not version — version is a free-text String column, so
    # sorting by it is lexicographic (e.g. "9" > "10"), not numeric.
    # Phase 26 organically pushed research_agent past version 9 while
    # iterating on template.md, exposing this as a real bug (both here
    # and in register_template's next_version calc above): the wrong
    # template could get selected for a live render once any agent's
    # version count crosses into double digits.
    return (
        db.query(PromptTemplate)
        .filter(PromptTemplate.agent_template_id == agent_template_id, PromptTemplate.status == "active")
        .order_by(PromptTemplate.created_at.desc())
        .first()
    )


def list_templates(db: Session):
    return db.query(PromptTemplate).all()

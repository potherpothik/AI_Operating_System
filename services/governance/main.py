from fastapi import FastAPI

from governance.db import Base, engine
from governance.security.api import router as security_router
from governance.audit.api import router as audit_router
from governance.approval.api import router as approval_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 1: Governance",
    description="Security Layer, Audit Logger, Human Approval Layer — the enforcement point every later phase assumes exists.",
)

app.include_router(security_router)
app.include_router(audit_router)
app.include_router(approval_router)


@app.get("/")
def root():
    return {"status": "ok", "phase": 1, "modules": ["security", "audit", "approval"]}

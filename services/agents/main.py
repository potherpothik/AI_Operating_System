from fastapi import FastAPI

from agents.db import Base, engine, SessionLocal
from agents.reasoning_engine.api import router as reasoning_router
from agents.reasoning_engine import capability_registry
from agents.odoo_agent import register as odoo_agent_register

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 5: Reasoning Engine & Odoo Agent",
    description="The shared execution loop every agent runs through, and the first live agent running on it.",
)

app.include_router(reasoning_router)


@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        capability_registry.load_all(db)
    finally:
        db.close()
    odoo_agent_register.ensure_template_registered()


@app.post("/capabilities/reload")
def reload_capabilities():
    db = SessionLocal()
    try:
        loaded = capability_registry.load_all(db)
    finally:
        db.close()
    return {"loaded": loaded}


@app.post("/odoo_agent/register")
def register_odoo_agent_template():
    return odoo_agent_register.ensure_template_registered()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 5}


@app.get("/")
def root():
    return {"status": "ok", "phase": 5, "modules": ["reasoning_engine", "odoo_agent"]}

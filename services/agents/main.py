from fastapi import FastAPI

from agents.db import Base, engine, SessionLocal
from agents.reasoning_engine.api import router as reasoning_router
from agents.reasoning_engine import capability_registry
from agents.odoo_agent import register as odoo_agent_register
from agents.database_agent import register as database_agent_register
from agents.planner import register as planner_register

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 5/7/8: Reasoning Engine, Odoo Agent, Database Agent & Planner",
    description="The shared execution loop every agent runs through, and the agents running on it.",
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
    database_agent_register.ensure_template_registered()
    planner_register.ensure_template_registered()


@app.post("/capabilities/reload")
def reload_capabilities():
    db = SessionLocal()
    try:
        loaded = capability_registry.load_all(db)
    finally:
        db.close()
    return {"loaded": loaded}


@app.get("/capabilities")
def list_capabilities():
    """
    Introspection endpoint: what Reasoning Engine currently has loaded and
    actually enforces (capability_registry.load_all(), the source of
    truth for local_precheck). Phase 8's Capability Registry service
    syncs from this over HTTP rather than reaching into this service's
    own filesystem — the same inter-service-over-HTTP discipline every
    other cross-service call in this system follows.
    """
    db = SessionLocal()
    try:
        rows = db.query(capability_registry.AgentCapabilityDef).all()
        return {
            "capabilities": [
                {
                    "agent_capability": r.agent_capability,
                    "allowed_actions": r.allowed_actions,
                    "forbidden_actions": r.forbidden_actions,
                    "requires_approval": r.requires_approval,
                    "classification_ceiling": r.classification_ceiling,
                    "template_id": r.template_id,
                }
                for r in rows
            ]
        }
    finally:
        db.close()


@app.post("/odoo_agent/register")
def register_odoo_agent_template():
    return odoo_agent_register.ensure_template_registered()


@app.post("/database_agent/register")
def register_database_agent_template():
    return database_agent_register.ensure_template_registered()


@app.post("/planner/register")
def register_planner_template():
    return planner_register.ensure_template_registered()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 5}


@app.get("/")
def root():
    return {"status": "ok", "phase": 5, "modules": ["reasoning_engine", "odoo_agent", "database_agent", "planner"]}

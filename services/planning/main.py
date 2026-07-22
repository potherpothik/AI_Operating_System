from fastapi import FastAPI

from planning.db import Base, engine
from planning.capability_registry.api import router as capability_router
from planning.planner.api import router as planner_router
from planning.workflows.api import router as workflows_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 8: Planner & Capability Registry",
    description="Automatic task routing — a live, versioned index of what agents exist, and the first agent that reasons over it instead of being told which one to use.",
)

app.include_router(capability_router)
app.include_router(planner_router)
app.include_router(workflows_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 30}


@app.get("/")
def root():
    return {"status": "ok", "phase": 30, "modules": ["capability_registry", "planner", "workflows"]}

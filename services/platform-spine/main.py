from fastapi import FastAPI

from platform_spine.db import Base, engine
from platform_spine.config_manager.api import router as config_router
from platform_spine.gateway.api import router as gateway_router
from platform_spine.gateway.openai_shim import router as openai_shim_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 2: Platform Spine",
    description="Configuration Manager, Gateway, Task Manager — the walking skeleton, calling Phase 1's Security Layer over real HTTP from the first request.",
)

app.include_router(config_router)
app.include_router(gateway_router)
app.include_router(openai_shim_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 2}


@app.get("/")
def root():
    return {"status": "ok", "phase": 2, "modules": ["config_manager", "gateway", "task_manager"]}

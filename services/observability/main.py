from fastapi import FastAPI

from observability.db import Base, engine
from observability.health_monitor.api import router as health_router
from observability.metrics_dashboard.api import router as metrics_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 13: Health Monitor & Metrics Dashboard",
    description="Read-only aggregation over data every prior phase already produces — liveness/readiness checks and operational metrics, never a write path to anything.",
)

app.include_router(health_router)
app.include_router(metrics_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 13}


@app.get("/")
def root():
    return {"status": "ok", "phase": 13, "modules": ["health_monitor", "metrics_dashboard"]}

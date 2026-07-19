from fastapi import FastAPI

from database.db import Base, engine
from database.database_connector.api import router as db_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 7: Data Execution Layer",
    description="Database Connector — the only module permitted to open connections to or execute queries against a real database.",
)

app.include_router(db_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 7}


@app.get("/")
def root():
    return {"status": "ok", "phase": 7, "modules": ["database_connector", "database_agent"]}

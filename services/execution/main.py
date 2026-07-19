from fastapi import FastAPI

from execution.db import Base, engine
from execution.shell_executor.api import router as shell_router
from execution.git_manager.api import router as git_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 6: Execution Layer",
    description="Shell Executor and Git Manager — the only modules permitted to touch a real filesystem or git history.",
)

app.include_router(shell_router)
app.include_router(git_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 6}


@app.get("/")
def root():
    return {"status": "ok", "phase": 6, "modules": ["shell_executor", "git_manager"]}

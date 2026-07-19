from fastapi import FastAPI

from assembly.db import Base, engine
from assembly.context_builder.api import router as context_router
from assembly.prompt_builder.api import router as prompt_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 4: Context & Prompt Assembly",
    description="Context Builder and Prompt Builder — what an agent sees, and how it's phrased.",
)

app.include_router(context_router)
app.include_router(prompt_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 4}


@app.get("/")
def root():
    return {"status": "ok", "phase": 4, "modules": ["context_builder", "prompt_builder"]}

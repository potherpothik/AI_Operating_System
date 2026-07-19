from fastapi import FastAPI

from knowledge.db import Base, engine
from knowledge.memory_manager.api import router as memory_router
from knowledge.vector_search.api import router as vector_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 3: Knowledge Substrate",
    description="Memory Manager and Vector Search — the knowledge substrate every future agent draws from.",
)

app.include_router(memory_router)
app.include_router(vector_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 3}


@app.get("/")
def root():
    return {"status": "ok", "phase": 3, "modules": ["memory_manager", "vector_search"]}

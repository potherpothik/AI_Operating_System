from fastapi import FastAPI

from knowledge_pipelines.db import Base, engine
from knowledge_pipelines.documentation_engine.api import router as docs_router
from knowledge_pipelines.erp_knowledge_engine.api import router as erp_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 9: Documentation & ERP Knowledge Engines",
    description="Real content into Vector Search and business memory — closing the knowledge gap every agent since Phase 5 has been operating with.",
)

app.include_router(docs_router)
app.include_router(erp_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 9}


@app.get("/")
def root():
    return {"status": "ok", "phase": 9, "modules": ["documentation_engine", "erp_knowledge_engine"]}

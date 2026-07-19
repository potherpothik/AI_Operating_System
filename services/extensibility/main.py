from fastapi import FastAPI

from extensibility.db import Base, engine
from extensibility.mcp_client.api import router as mcp_router
from extensibility.plugin_system.api import router as plugin_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 12: MCP Client & Plugin System",
    description="Extensibility infrastructure: consuming external MCP servers as tools, and adding new agents/tool adapters without modifying core code — both governed by the same Security Layer and Human Approval Layer gating as everything else.",
)

app.include_router(mcp_router)
app.include_router(plugin_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 12}


@app.get("/")
def root():
    return {"status": "ok", "phase": 12, "modules": ["mcp_client", "plugin_system"]}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from control_ui.api import router as ui_router

app = FastAPI(
    title="AI Orchestration Layer — Phase 24: Control UI BFF",
    description="Aggregation and governed-write proxy for the web operator console — holds no orchestration logic of its own, everything real lives in the existing services it fronts.",
)

# Dev-only: the Vite dev server runs on a different origin than this BFF.
# Production serves the built shell from the same origin as the BFF
# (Phase 24 doc §6), where this middleware is a no-op.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ui_router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 24}


@app.get("/")
def root():
    return {"status": "ok", "phase": 24, "modules": ["control_ui"]}

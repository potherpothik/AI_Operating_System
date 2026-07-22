from fastapi import FastAPI

from identity.api import router as identity_router

app = FastAPI(
    title="AI Orchestration Layer — Phase 31: Identity Provider",
    description="A real, self-hosted OpenID Connect provider — the team/GPU-day hardening phase's real replacement for Phase 2's token-stub auth.",
)

app.include_router(identity_router)


@app.get("/")
def root():
    return {"status": "ok", "phase": 31, "modules": ["identity"]}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 31}

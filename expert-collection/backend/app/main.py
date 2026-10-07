"""FastAPI app entry point (Phase 1: expert conversation + DAG collection only).

Run with: uvicorn app.main:app --reload --port 8000  (from expert-collection/backend/)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import admin, annotations, datasets, expert_workflows, experiments, settings, voice, phase3b_rules, phase3b_advanced, phase3b_conflict

app = FastAPI(title="Expert Workflow Collection API", version="0.1.0")

# Local Vite dev server default ports + production tunnel hostname
# (workflow-data.inkpath.cc -> cloudflared -> vite dev on :8804 -> /api proxied to :8803).
# Only allow these -- do NOT use ["*"] with allow_credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8804",
        "http://127.0.0.1:8804",
        "https://workflow-data.inkpath.cc",
    ],
    allow_credentials=True,
    # Every route this API actually defines, plus OPTIONS for the CORS preflight itself.
    # allow_origins above is the real access-control boundary (an explicit hostname list,
    # not "*"); this is defense in depth, not load-bearing on its own.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(expert_workflows.router)
app.include_router(datasets.router)
app.include_router(annotations.router)
app.include_router(experiments.router)
app.include_router(admin.router)
app.include_router(settings.router)
app.include_router(voice.router)
app.include_router(phase3b_rules.router)
app.include_router(phase3b_advanced.router)
app.include_router(phase3b_conflict.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}

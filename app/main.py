"""MatchDay Copilot API — smart stadium operations for FIFA World Cup 2026.

Run:  uvicorn app.main:app --reload
Docs: http://127.0.0.1:8000/docs
UI:   http://127.0.0.1:8000/
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import llm
from app.core import engine, nlg
from app.models import AssistRequest, AssistResponse, Incident, IncidentReport
from app.security import SECURITY_HEADERS, RateLimiter, sanitize
from app.services import schedule, stadium
from app.services.incidents import IncidentLog

app = FastAPI(
    title="MatchDay Copilot",
    description="GenAI-powered smart stadium & tournament operations assistant",
    version="1.0.0",
)

_STATIC = Path(__file__).resolve().parent.parent / "static"
_START = time.monotonic()

incident_log = IncidentLog()
rate_limiter = RateLimiter(limit=30, window_seconds=60)


def current_tick() -> int:
    """Simulation clock: one telemetry tick per 5 seconds of wall time."""
    return int((time.monotonic() - _START) / 5)


@app.middleware("http")
async def guard(request: Request, call_next):
    client = request.client.host if request.client else "unknown"
    if request.url.path.startswith("/api") and not rate_limiter.allow(client):
        response = JSONResponse(
            {"detail": "Rate limit exceeded. Try again in a minute."},
            status_code=429,
        )
    else:
        response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)  # on every response, incl. 429
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "llm": llm.provider() or "rules-only"}


@app.post("/api/assist", response_model=AssistResponse)
def assist(req: AssistRequest) -> AssistResponse:
    """One assistant turn: classify → decide → render → (optionally) polish."""
    req.message = sanitize(req.message)
    if not req.message:
        raise HTTPException(status_code=422, detail="Message is empty after sanitization.")
    if req.zone is not None:
        req.zone = sanitize(req.zone, limit=32).lower() or None
        if req.zone and req.zone not in stadium.zone_ids():
            req.zone = None  # unknown zone → engine falls back to stadium-wide picks

    decision = engine.decide(req, current_tick())
    draft = nlg.render(decision, req)
    message, generated_by = llm.polish(draft, req.message, req.language.value)
    return AssistResponse(
        intent=decision.intent,
        priority=decision.priority,
        message=message,
        reasoning=decision.reasoning,
        actions=decision.actions,
        generated_by=generated_by,
    )


@app.get("/api/stadium/state")
def stadium_state() -> dict:
    return stadium.state(current_tick())


@app.get("/api/matches")
def matches() -> list[dict]:
    return schedule.matches()


@app.get("/api/matches/next")
def match_next() -> dict:
    match = schedule.next_match()
    if match is None:
        raise HTTPException(status_code=404, detail="No upcoming matches.")
    return match


@app.post("/api/incidents", response_model=Incident, status_code=201)
def report_incident(report: IncidentReport) -> Incident:
    report.description = sanitize(report.description)
    report.zone = sanitize(report.zone, limit=32).lower()
    if report.zone not in stadium.zone_ids():
        raise HTTPException(status_code=422, detail="Unknown zone.")
    if len(report.description) < 3:
        raise HTTPException(status_code=422, detail="Description too short.")
    return incident_log.report(report)


@app.get("/api/incidents", response_model=list[Incident])
def list_incidents() -> list[Incident]:
    return incident_log.all()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


app.mount("/static", StaticFiles(directory=_STATIC), name="static")

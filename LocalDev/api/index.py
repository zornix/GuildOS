"""
FraternityOS Backend — FastAPI + Supabase
==========================================
Entry point: api/index.py (Vercel serverless function)

Deploy:  vercel --prod
Local:   uvicorn api.index:app --reload
"""

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings, Settings
from api.db import get_supabase
from api.health_checks import build_health_payload


def production_config_violations(s: Settings) -> list[str]:
    """List every prod-misconfiguration in `s`. Empty in dev/preview or when clean."""
    if not s.is_production:
        return []
    violations: list[str] = []
    if s.JWT_SECRET == "local-dev-secret":
        violations.append("JWT_SECRET is still the insecure local default")
    if not s.DATABASE_URL:
        violations.append("DATABASE_URL is unset (prod runs on the direct-Postgres path, ADR-0002)")
    if s.DEV_AUTH_BYPASS:
        violations.append("DEV_AUTH_BYPASS is enabled")
    return violations


# Fail the Vercel deploy loudly rather than boot a misconfigured production
# function (imp-tenant-guards.md D5). Preview deployments are deliberately not
# guarded. Import-time so a bad config never serves a request.
_violations = production_config_violations(settings)
if _violations:
    raise RuntimeError(
        "Refusing to boot in production — fix: " + "; ".join(_violations)
    )

from api.auth.api.router import router as auth_router
from api.members.api.router import router as members_router
from api.cron.api.router import router as cron_router
from api.standing.api.router import router as standing_router
from api.announcements.api.router import router as announcements_router
from api.attendance.api.router import (
    router as attendance_router,
    checkin_links_router,
    checkin_page_router,
    excuses_router,
)
from api.bylaws.api.router import router as bylaws_router
from api.events.api.router import router as events_router
from api.memberadmin.api.router import router as memberadmin_router
from api.nl_controller.api.router import router as nl_controller_router
from api.rbac.api.router import router as rbac_router
from api.recruitment.api.router import router as recruitment_router
from api.tasks.api.router import router as tasks_router
from api.tasks.api.operations import router as operations_router
from api.treasury.api.router import router as treasury_router
from api.treasury.api.fines_legacy import router as fines_router
from api.calendar.api.router import router as calendar_router
from api.instrumentation.api.router import router as usage_router
from api.initiatives.api.router import router as initiatives_router

app = FastAPI(
    title="FraternityOS API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(events_router, prefix="/api/events", tags=["Events"])
app.include_router(attendance_router, prefix="/api/attendance", tags=["Attendance"])
app.include_router(excuses_router, prefix="/api/excuses", tags=["Excuses"])

app.include_router(fines_router, prefix="/api/fines", tags=["Fines"])
app.include_router(members_router, prefix="/api/members", tags=["Members"])
app.include_router(checkin_page_router, prefix="/c", tags=["Check-In Page"])
app.include_router(checkin_links_router, prefix="/api/checkin-links", tags=["Check-In Links"])
app.include_router(cron_router, prefix="/api/cron", tags=["Cron"])
app.include_router(standing_router, prefix="/api/standing", tags=["Standing"])
app.include_router(memberadmin_router, prefix="/api/memberadmin", tags=["MemberAdmin"])

app.include_router(treasury_router, prefix="/api/treasury", tags=["Treasury"])
app.include_router(rbac_router, prefix="/api/rbac", tags=["RBAC"])
app.include_router(tasks_router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(operations_router, prefix="/api/operations", tags=["Operations"])
app.include_router(announcements_router, prefix="/api/announcements", tags=["Announcements"])
app.include_router(recruitment_router, prefix="/api/recruitment", tags=["Recruitment"])
app.include_router(bylaws_router, prefix="/api/bylaws", tags=["Bylaws"])
app.include_router(nl_controller_router, prefix="/api/nl-controller", tags=["NL Controller"])
app.include_router(calendar_router, prefix="/api/calendar", tags=["Calendar"])
app.include_router(usage_router, prefix="/api/usage", tags=["Usage"])
app.include_router(initiatives_router, prefix="/api/initiatives", tags=["Initiatives"])


@app.get("/api/health")
async def health():
    return await asyncio.to_thread(build_health_payload, get_supabase())

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
from api.platform.db import get_db
from api.health_checks import build_health_payload
from api.observability import init_observability


MIN_JWT_SECRET_LENGTH = 32
MIN_CRON_SECRET_LENGTH = 16
VALID_DELIVERY_MODES = ("dry_run", "twilio")


def production_config_violations(s: Settings) -> list[str]:
    """List every deploy-misconfiguration in `s`. Empty locally or when clean.

    Guards **production and preview** (`is_deployed`). Preview deploys are public
    URLs that inherit the project's env vars, so an unguarded preview with
    `DEV_AUTH_BYPASS=1` was a full authentication bypass on a reachable host.

    Each entry names the variable and the fix — this text is the only thing an
    operator sees in a failed Vercel build log.
    """
    if not s.is_deployed:
        return []
    violations: list[str] = []

    # Both the known dev defaults and any low-entropy value. `startswith` (not
    # `==`) because .env.example long shipped "local-dev-secret-key-change-in-prod",
    # which passed an exact-match check.
    if s.JWT_SECRET.startswith("local-dev-secret") or len(s.JWT_SECRET) < MIN_JWT_SECRET_LENGTH:
        violations.append(
            f"JWT_SECRET is a known dev default or shorter than {MIN_JWT_SECRET_LENGTH} chars "
            "— set it to a random 32+ character secret"
        )

    if not s.DATABASE_URL:
        violations.append("DATABASE_URL is unset (prod runs on the direct-Postgres path, ADR-0002)")

    if s.DEV_AUTH_BYPASS:
        violations.append("DEV_AUTH_BYPASS is enabled — unset it, it disables authentication")

    # Cron endpoints authenticate solely on this shared secret; empty means every
    # cron route is either open or dead, and neither is acceptable in a deploy.
    if not s.CRON_SECRET or len(s.CRON_SECRET) < MIN_CRON_SECRET_LENGTH:
        violations.append(
            f"CRON_SECRET is unset or shorter than {MIN_CRON_SECRET_LENGTH} chars "
            "— set a random secret matching the Vercel cron caller"
        )

    # FRONTEND_URL is the CORS allowlist below, so a localhost value in a deploy
    # both breaks the real origin and trusts a developer machine.
    if "localhost" in s.FRONTEND_URL or "127.0.0.1" in s.FRONTEND_URL:
        violations.append(
            f"FRONTEND_URL points at localhost ({s.FRONTEND_URL}) "
            "— set the deployed origin; it is the CORS allowlist"
        )

    if s.MESSAGE_DELIVERY_MODE not in VALID_DELIVERY_MODES:
        # A typo here silently downgrades every send to a no-op.
        violations.append(
            f"MESSAGE_DELIVERY_MODE={s.MESSAGE_DELIVERY_MODE!r} is not one of "
            f"{' | '.join(VALID_DELIVERY_MODES)} — a typo silently disables all SMS"
        )
    elif s.MESSAGE_DELIVERY_MODE == "twilio":
        missing = [
            name
            for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER")
            if not getattr(s, name)
        ]
        if missing:
            violations.append(
                "MESSAGE_DELIVERY_MODE=twilio but " + ", ".join(missing) + " is unset "
                "— set it or fall back to MESSAGE_DELIVERY_MODE=dry_run"
            )

    return violations


# Fail the Vercel deploy loudly rather than boot a misconfigured function
# (imp-tenant-guards.md D5). Import-time so a bad config never serves a request.
_violations = production_config_violations(settings)
if _violations:
    raise RuntimeError(
        f"Refusing to boot in {settings.VERCEL_ENV} — fix: " + "; ".join(_violations)
    )

# Domains whose routes live in one module mount that module's router directly.
from api.auth.api.auth import router as auth_router
from api.members.api.members import router as members_router
from api.chapters.api.chapters import router as chapters_router
from api.cron.api.cron import router as cron_router
from api.announcements.api.announcements import router as announcements_router
from api.bylaws.api.documents import router as bylaws_router
from api.nl_controller.api.commands import router as nl_controller_router
from api.rbac.api.roles import router as rbac_router
from api.recruitment.api.pipeline import router as recruitment_router
from api.calendar.api.calendar import router as calendar_router
from api.instrumentation.api.usage import router as usage_router
from api.initiatives.api.initiatives import router as initiatives_router
from api.tasks.api.operations import router as operations_router
from api.treasury.api.fines_legacy import router as fines_router

# MemberAdmin owns standing; /api/standing stays its own mount for the frontend.
from api.memberadmin.api.scores import router as memberadmin_router
from api.memberadmin.api.standing import router as standing_router

# Domains with several sub-routers keep a real aggregator that fixes their order.
from api.attendance.api.router import (
    router as attendance_router,
    checkin_links_router,
    checkin_page_router,
    excuses_router,
)
from api.events.api.router import router as events_router
from api.tasks.api.router import router as tasks_router
from api.treasury.api.router import router as treasury_router

# Swagger and the OpenAPI schema stay on locally (CLAUDE.md documents /api/docs
# for dev) but are withdrawn from every deploy — the schema enumerates the whole
# authenticated surface and there is no reason to publish it.
app = FastAPI(
    title="FraternityOS API",
    version="0.1.0",
    docs_url=None if settings.is_deployed else "/api/docs",
    openapi_url=None if settings.is_deployed else "/api/openapi.json",
)

init_observability(app)

# localhost is a dev convenience only; a deploy trusts FRONTEND_URL alone.
_allowed_origins = [settings.FRONTEND_URL]
if not settings.is_deployed and "http://localhost:3000" not in _allowed_origins:
    _allowed_origins.append("http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
app.include_router(chapters_router, prefix="/api/chapters", tags=["Chapters"])
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
    return await asyncio.to_thread(build_health_payload, get_db())

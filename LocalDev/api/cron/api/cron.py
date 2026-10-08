"""Scheduled endpoints. Every route here is gated by CRON_SECRET (see auth.py).

Vercel Cron issues **GET** requests only, and attaches
`Authorization: Bearer $CRON_SECRET` automatically when that env var is set — so
GET is the scheduled entrypoint for the outbox drain. POST has its own handler
for manual/ops invocation (curl, a runbook step); both share the drain helper
and the identical auth dependency.

The schedule itself lives in the project-root vercel.json `crons` block. It used
to live in api/vercel.json, which Vercel never reads (GTMLarpChecklist 3.6).
"""

import asyncio

from fastapi import APIRouter, Depends

from api.cron.auth import require_cron_secret
from api.cron.services.outbox_drain import drain_outbox

# Router-level dependency: every cron route, present and future, is authenticated.
router = APIRouter(dependencies=[Depends(require_cron_secret)])


@router.get("/process-fines")
def cron_process_fines():
    """DISABLED: fines are never automatic.

    The route stays registered (route-registration regression tests) but is a
    no-op. Fine issuance is the manual, permission-gated POST /api/fines/issue
    (≥24h after a required event; flat $25), driven by GET /api/fines/missed/{event_id}.
    """
    return {
        "status": "disabled",
        "reason": "V1: fines are never automatic; use POST /api/fines/issue",
    }


async def _drain_outbox():
    return await asyncio.to_thread(drain_outbox)


@router.get("/drain-outbox")
async def cron_drain_outbox_scheduled():
    """Deliver queued messages from the authenticated scheduled job."""
    return await _drain_outbox()


@router.post("/drain-outbox")
async def cron_drain_outbox_manual():
    """Deliver queued messages on an authenticated operator request."""
    return await _drain_outbox()

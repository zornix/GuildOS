"""Scheduled endpoints. Every route here is gated by CRON_SECRET (see auth.py).

Vercel Cron issues **GET** requests only, and attaches
`Authorization: Bearer $CRON_SECRET` automatically when that env var is set — so
GET is the scheduled entrypoint for the outbox drain. POST is registered on the
same handler purely for manual/ops invocation (curl, a runbook step); it carries
the identical auth dependency.

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
async def cron_process_fines():
    """DISABLED (GreekOS V1, spec §5 Fines): fines are never automatic.

    The route stays registered (route-registration regression tests) but is a
    no-op. Fine issuance is the manual, permission-gated POST /api/fines/issue
    (≥24h after a required event; flat $25), driven by GET /api/fines/missed/{event_id}.
    """
    return {
        "status": "disabled",
        "reason": "V1: fines are never automatic; use POST /api/fines/issue",
    }


@router.api_route("/drain-outbox", methods=["GET", "POST"])
async def cron_drain_outbox():
    """Deliver pending message_outbox rows (checklist 2.1).

    GET is the Vercel Cron entrypoint (crons only issue GET); POST is the manual
    ops path. Returns {processed, sent, simulated, failed} for this batch.
    """
    return await asyncio.to_thread(drain_outbox)

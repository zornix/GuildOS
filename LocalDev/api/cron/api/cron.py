from fastapi import APIRouter

router = APIRouter()


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

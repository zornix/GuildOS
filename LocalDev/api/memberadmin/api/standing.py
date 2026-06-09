from fastapi import APIRouter, Depends

from api.dependencies import require_officer
from api.memberadmin.services.standing import compute_member_standings

router = APIRouter()


@router.get("/")
async def get_standings(officer=Depends(require_officer)):
    """
    Simple member standing based on explicit rules:
      - good_standing: no issues
      - warning: 1 unpaid fine OR 1+ unexcused absence
      - delinquent: 2+ unpaid fines OR $50+ unpaid OR 3+ unexcused absences
    """
    return await compute_member_standings(officer["chapter_id"])

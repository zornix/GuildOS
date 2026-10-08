from fastapi import APIRouter, Depends

from api.memberadmin.services.standing import compute_member_standings
from api.rbac.auth import require_permission

STANDING_VIEW_ALL = "standing:view_all"

router = APIRouter()


@router.get("/")
def get_standings(officer=Depends(require_permission(STANDING_VIEW_ALL))):
    """
    Simple member standing based on explicit rules:
      - good_standing: no issues
      - warning: 1 unpaid fine OR 1+ unexcused absence
      - delinquent: 2+ unpaid fines OR $50+ unpaid OR 3+ unexcused absences
    """
    return compute_member_standings(officer["chapter_id"])

"""Chapter onboarding endpoints (#74).

    POST /api/chapters                    create chapter + first officer
    POST /api/chapters/{id}/roster        multipart CSV roster import

`scripts/provision_chapter.py` still works and is still the path for a chapter
that needs a password set by hand; this is the self-serve one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile

from api.chapters.auth import authorize_chapter_create
from api.chapters.services.onboarding import RosterFileError, create_chapter, import_roster
from api.platform.db import get_db
from api.rbac.auth import require_permission

from .schemas import CreateChapterRequest

router = APIRouter()

# A roster CSV is a few hundred rows of text; anything larger is a mistake or an
# attack, and we read the whole body into memory.
MAX_ROSTER_BYTES = 1_000_000


@router.post("", status_code=201)
async def create_chapter_endpoint(
    body: CreateChapterRequest,
    request: Request,
    authorization: str | None = Header(default=None),
):
    """Create a chapter and its first officer. Returns a one-time setup code.

    No password is accepted: the officer claims the account by redeeming the
    setup code at POST /api/auth/redeem-setup-code, exactly like an invitee.
    """
    authorize_chapter_create(request, authorization)
    try:
        return create_chapter(
            get_db(),
            name=body.name,
            organization=body.organization,
            school=body.school,
            officer_name=body.officer_name,
            officer_email=str(body.officer_email).strip().lower(),
            officer_phone=body.officer_phone,
        )
    except Exception as exc:
        message = str(exc)
        if "chapter_name_taken" in message:
            raise HTTPException(409, f"A chapter named {body.name!r} already exists")
        if "officer_email_taken" in message or "members_email_key" in message:
            raise HTTPException(409, "That email already belongs to a member")
        raise


@router.post("/{chapter_id}/roster")
async def import_roster_endpoint(
    chapter_id: str,
    file: UploadFile = File(...),
    officer=Depends(require_permission("members:invite")),
):
    """Import a roster CSV (name,email,phone[,role]) as invited members.

    All-or-nothing: 422 with row numbers and zero inserts if any row is bad.
    Emails already in this chapter are skipped and listed in `skipped`.
    """
    if str(officer["chapter_id"]) != str(chapter_id):
        # Same 404 for "no such chapter" and "someone else's chapter".
        raise HTTPException(404, "Chapter not found")

    raw = await file.read()
    if len(raw) > MAX_ROSTER_BYTES:
        raise HTTPException(413, "Roster file is too large")

    try:
        return import_roster(get_db(), chapter_id=chapter_id, raw=raw)
    except RosterFileError as exc:
        raise HTTPException(422, {"message": "No members were imported", "errors": exc.errors})

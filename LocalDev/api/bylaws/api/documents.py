"""Bylaws HTTP surface. Mounted under `/api/bylaws` by router.py."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.bylaws.api.schemas import BylawsDocumentCreate, BylawsQuery
from api.bylaws.auth import BYLAWS_ADMIN, BYLAWS_QUERY, require_permission
from api.bylaws.services import documents as svc
from api.bylaws.services.documents import get_bylaws_db

router = APIRouter()


@router.get("/documents")
async def list_documents(user=Depends(require_permission(BYLAWS_QUERY))):
    return svc.list_documents(get_bylaws_db(), chapter_id=user["chapter_id"])


@router.post("/documents")
async def create_document(
    body: BylawsDocumentCreate,
    user=Depends(require_permission(BYLAWS_ADMIN)),
):
    return svc.create_document(
        get_bylaws_db(),
        chapter_id=user["chapter_id"],
        title=body.title,
        content=body.content,
        actor_id=user["id"],
    )


@router.post("/query")
async def query_bylaws(
    body: BylawsQuery,
    user=Depends(require_permission(BYLAWS_QUERY)),
):
    return svc.query_bylaws(
        get_bylaws_db(), chapter_id=user["chapter_id"], question=body.question
    )

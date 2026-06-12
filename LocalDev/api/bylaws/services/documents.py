"""Bylaws documents service."""

from __future__ import annotations

from api.db import get_supabase_admin


def get_bylaws_db():
    return get_supabase_admin()


def create_document(
    sb, *, chapter_id: str, title: str, content: str, actor_id: str
) -> dict:
    result = (
        sb.table("bylaws_documents")
        .insert(
            {
                "chapter_id": chapter_id,
                "title": title,
                "content": content,
                "created_by": actor_id,
            }
        )
        .execute()
    )
    data = result.data
    return data[0] if isinstance(data, list) else data


def list_documents(sb, *, chapter_id: str) -> list[dict]:
    return (
        sb.table("bylaws_documents")
        .select("id, chapter_id, title, version, created_at, updated_at")
        .eq("chapter_id", chapter_id)
        .order("created_at", desc=True)
        .execute()
    ).data or []


def query_bylaws(sb, *, chapter_id: str, question: str) -> dict:
    """Honest stub — there is no retrieval or answering layer yet.

    TODO(bylaws): retrieval over bylaws_documents + an answering layer. Until
    then this returns not_implemented; it must NEVER fabricate an answer.
    """
    doc_count = len(list_documents(sb, chapter_id=chapter_id))
    return {
        "status": "not_implemented",
        "question": question,
        "answer": None,
        "documents_available": doc_count,
        "detail": "Bylaws Q&A is not implemented yet; no answer was generated.",
    }

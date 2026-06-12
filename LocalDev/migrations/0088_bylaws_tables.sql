-- Bylaws service: document storage only. No RAG pipeline, no retrieval index —
-- the query endpoint is an honest stub until one exists.

CREATE TABLE IF NOT EXISTS bylaws_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    created_by UUID REFERENCES members(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_bylaws_documents_chapter_id ON bylaws_documents(chapter_id);
CREATE INDEX IF NOT EXISTS ix_bylaws_documents_created_at ON bylaws_documents(created_at);

ALTER TABLE bylaws_documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS bylaws_documents_select_chapter ON bylaws_documents;
CREATE POLICY bylaws_documents_select_chapter ON bylaws_documents
    FOR SELECT
    USING (chapter_id = rbac_request_chapter_id());

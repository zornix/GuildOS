"use client";
import { useState } from "react";
import { useApi } from "../hooks/use-api";
import { usePermissions } from "../hooks/use-permissions";
import { api } from "../lib/api-client";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Btn } from "../components/ui/btn";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { ListRow } from "../components/ui/list-row";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import type { BylawsDocument, BylawsQueryResult } from "../lib/types";

export function BylawsPage() {
  const { can } = usePermissions();
  const docs = useApi<BylawsDocument[]>(() => api.getBylawsDocuments(), []);
  const [question, setQuestion] = useState("");
  const [queryResult, setQueryResult] = useState<BylawsQueryResult | null>(null);
  const [asking, setAsking] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const ask = async () => {
    if (!question.trim()) return;
    setAsking(true);
    setActionError(null);
    try {
      setQueryResult(await api.queryBylaws(question.trim()));
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setAsking(false);
    }
  };

  const addDocument = async () => {
    if (!title.trim() || !content.trim()) return;
    setSaving(true);
    setActionError(null);
    try {
      await api.createBylawsDocument({ title: title.trim(), content: content.trim() });
      setTitle("");
      setContent("");
      await docs.reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const data = docs.data || [];

  return (
    <div>
      <Card style={{ marginBottom: tokens.space[5] }}>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Ask the Bylaws</h3>
        <Textarea
          label="Question"
          rows={2}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="e.g. Can chapter elections be held remotely?"
        />
        <Btn onClick={ask} disabled={asking || !question.trim()}>Ask</Btn>
        {queryResult && (
          // The backend deliberately returns no answer until a real retrieval
          // layer exists — surface that honestly instead of fabricating one.
          <div style={{
            marginTop: tokens.space[4],
            padding: tokens.space[4],
            borderRadius: tokens.radius.md,
            background: tokens.color.bg,
            border: `1px solid ${tokens.color.border}`,
            color: tokens.color.textMuted,
            fontSize: tokens.font.sizeMd,
          }}>
            {queryResult.detail} ({queryResult.documents_available} document{queryResult.documents_available === 1 ? "" : "s"} on file)
          </div>
        )}
      </Card>

      {can("bylaws:admin") && (
        <Card style={{ marginBottom: tokens.space[5] }}>
          <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Add Document</h3>
          <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Chapter Bylaws 2026" />
          <Textarea label="Content" rows={5} value={content} onChange={(e) => setContent(e.target.value)} placeholder="Paste the bylaws text…" />
          <Btn onClick={addDocument} disabled={saving || !title.trim() || !content.trim()}>Save Document</Btn>
        </Card>
      )}

      <Card>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Documents</h3>
        {actionError && (
          <div style={{ color: tokens.color.danger, fontSize: tokens.font.sizeSm, marginBottom: tokens.space[3] }}>{actionError}</div>
        )}
        {docs.loading ? (
          <LoadingState />
        ) : docs.error ? (
          <EmptyState message={docs.error} />
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {data.map((d) => (
              <ListRow
                key={d.id}
                primary={d.title}
                secondary={`Added ${new Date(d.created_at).toLocaleDateString()} · ${d.content.length.toLocaleString()} characters`}
              />
            ))}
            {data.length === 0 && <EmptyState message="No bylaws documents uploaded yet" />}
          </div>
        )}
      </Card>
    </div>
  );
}

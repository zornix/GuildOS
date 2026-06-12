"use client";
import { useState } from "react";
import { useApi } from "../hooks/use-api";
import { usePermissions } from "../hooks/use-permissions";
import { api } from "../lib/api-client";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { SegmentedControl } from "../components/ui/segmented-control";
import { ListRow } from "../components/ui/list-row";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import type { Announcement, AnnouncementAudience } from "../lib/types";

const AUDIENCE_LABELS: Record<AnnouncementAudience, string> = {
  chapter: "Whole Chapter",
  officers: "Officers",
  members_with_balance: "Members With Balance",
};

export function AnnouncementsPage() {
  const { can } = usePermissions();
  const announcements = useApi<Announcement[]>(() => api.getAnnouncements(), []);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [audience, setAudience] = useState<AnnouncementAudience>("chapter");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const createDraft = async () => {
    if (!title.trim() || !body.trim()) return;
    setSaving(true);
    setActionError(null);
    try {
      await api.createAnnouncement({ title: title.trim(), body: body.trim(), audience });
      setTitle("");
      setBody("");
      await announcements.reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const send = async (id: string) => {
    setActionError(null);
    try {
      await api.sendAnnouncement(id);
      await announcements.reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  const data = announcements.data || [];

  return (
    <div>
      {can("announcements:create") && (
        <Card style={{ marginBottom: tokens.space[5] }}>
          <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>New Announcement</h3>
          <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Dues reminder" />
          <Textarea label="Body" rows={3} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write the announcement…" />
          <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, marginBottom: tokens.space[1] }}>Audience</div>
          <SegmentedControl<AnnouncementAudience>
            options={[
              { value: "chapter", label: AUDIENCE_LABELS.chapter },
              { value: "officers", label: AUDIENCE_LABELS.officers },
              { value: "members_with_balance", label: AUDIENCE_LABELS.members_with_balance },
            ]}
            value={audience}
            onChange={setAudience}
          />
          <Btn onClick={createDraft} disabled={saving || !title.trim() || !body.trim()}>Save Draft</Btn>
        </Card>
      )}

      <Card>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Announcements</h3>
        {actionError && (
          <div style={{ color: tokens.color.danger, fontSize: tokens.font.sizeSm, marginBottom: tokens.space[3] }}>{actionError}</div>
        )}
        {announcements.loading ? (
          <LoadingState />
        ) : announcements.error ? (
          <EmptyState message={announcements.error} />
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {data.map((a) => (
              <ListRow
                key={a.id}
                primary={a.title}
                secondary={`${AUDIENCE_LABELS[a.audience] ?? a.audience} · ${a.status === "sent" && a.sent_at ? `sent ${new Date(a.sent_at).toLocaleString()}` : a.body}`}
                right={
                  <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
                    {a.status === "draft" && can("announcements:send") && (
                      <Btn style={{ padding: "4px 10px", fontSize: tokens.font.sizeSm }} onClick={() => send(a.id)}>Send</Btn>
                    )}
                    <Badge color={a.status === "sent" ? "green" : "gray"}>{a.status}</Badge>
                  </div>
                }
              />
            ))}
            {data.length === 0 && <EmptyState message="No announcements yet" />}
          </div>
        )}
      </Card>
    </div>
  );
}

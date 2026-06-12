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
import { Avatar } from "../components/ui/avatar";
import { ListRow } from "../components/ui/list-row";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import type { Recruit, RecruitStage } from "../lib/types";

const STAGES: { value: RecruitStage; label: string; color: "green" | "red" | "yellow" | "blue" | "purple" | "gray" }[] = [
  { value: "lead", label: "Lead", color: "gray" },
  { value: "contacted", label: "Contacted", color: "blue" },
  { value: "attended_event", label: "Attended Event", color: "yellow" },
  { value: "bid_extended", label: "Bid Extended", color: "purple" },
  { value: "bid_accepted", label: "Bid Accepted", color: "green" },
  { value: "dropped", label: "Dropped", color: "red" },
];

const NEXT_STAGE: Partial<Record<RecruitStage, RecruitStage>> = {
  lead: "contacted",
  contacted: "attended_event",
  attended_event: "bid_extended",
  bid_extended: "bid_accepted",
};

function stageMeta(stage: RecruitStage) {
  return STAGES.find((s) => s.value === stage) ?? STAGES[0];
}

export function RecruitmentPage() {
  const { can, loading: permsLoading } = usePermissions();
  const canView = can("recruitment:pipeline:view");
  const recruits = useApi<Recruit[]>(
    () => (canView ? api.getRecruits() : Promise.resolve([])),
    [canView],
  );
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (permsLoading) return <LoadingState />;
  if (!canView) {
    return (
      <Card style={{ textAlign: "center", color: tokens.color.textMuted, padding: tokens.space[8] }}>
        Recruitment pipeline access required to view this page.
      </Card>
    );
  }

  const addRecruit = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setActionError(null);
    try {
      await api.createRecruit({ name: name.trim(), email: email.trim() || undefined });
      setName("");
      setEmail("");
      await recruits.reload();
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const setStage = async (id: string, stage: RecruitStage) => {
    setActionError(null);
    try {
      await api.updateRecruitStage(id, stage);
      await recruits.reload();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  const data = recruits.data || [];
  const canUpdate = can("recruitment:pipeline:update");

  return (
    <div>
      {canUpdate && (
        <Card style={{ marginBottom: tokens.space[5] }}>
          <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Add Recruit</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: tokens.space[3] }}>
            <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Recruit name" />
            <Input label="Email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@school.edu" />
          </div>
          <Btn onClick={addRecruit} disabled={saving || !name.trim()}>Add to Pipeline</Btn>
        </Card>
      )}

      <Card>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Pipeline</h3>
        {actionError && (
          <div style={{ color: tokens.color.danger, fontSize: tokens.font.sizeSm, marginBottom: tokens.space[3] }}>{actionError}</div>
        )}
        {recruits.loading ? (
          <LoadingState />
        ) : recruits.error ? (
          <EmptyState message={recruits.error} />
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {data.map((r) => {
              const meta = stageMeta(r.stage);
              const next = NEXT_STAGE[r.stage];
              return (
                <ListRow
                  key={r.id}
                  left={<Avatar name={r.name} />}
                  primary={r.name}
                  secondary={[r.email, r.notes].filter(Boolean).join(" · ") || "No contact info"}
                  right={
                    <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
                      {canUpdate && next && (
                        <Btn variant="ghost" style={{ padding: "4px 10px", fontSize: tokens.font.sizeSm }} onClick={() => setStage(r.id, next)}>
                          → {stageMeta(next).label}
                        </Btn>
                      )}
                      {canUpdate && r.stage !== "dropped" && r.stage !== "bid_accepted" && (
                        <Btn variant="danger" style={{ padding: "4px 10px", fontSize: tokens.font.sizeSm }} onClick={() => setStage(r.id, "dropped")}>
                          Drop
                        </Btn>
                      )}
                      <Badge color={meta.color}>{meta.label}</Badge>
                    </div>
                  }
                />
              );
            })}
            {data.length === 0 && <EmptyState message="No recruits in the pipeline yet" />}
          </div>
        )}
      </Card>
    </div>
  );
}

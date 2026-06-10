"use client";
import { tokens } from "../../../config/theme/tokens";
import { Card } from "../../ui/card";
import { Icon } from "../../ui/icon";
import { Badge } from "../../ui/badge";
import { Btn } from "../../ui/btn";
import { api } from "../../../lib/api-client";
import type { Excuse } from "../../../lib/types";

interface PendingExcusesWidgetProps {
  excuses: Excuse[] | null;
  loading: boolean;
  error: string | null;
  onReload: () => void;
}

export function PendingExcusesWidget({ excuses, loading, error, onReload }: PendingExcusesWidgetProps) {
  const pending = (excuses || []).filter((e) => e.status === "pending");

  return (
    <Card>
      <div style={{ fontSize: tokens.font.sizeXl, fontWeight: tokens.font.weightBold, color: tokens.color.text, marginBottom: 14, display: "flex", alignItems: "center", gap: tokens.space[2] }}>
        <Icon type="file" /> Pending Excuses
      </div>
      {loading && !pending.length ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>Loading excuses…</div>
      ) : error ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>Could not load excuses. Use Retry above.</div>
      ) : pending.length === 0 ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>All clear</div>
      ) : (
        pending.slice(0, 5).map((exc) => (
          <div key={exc.id} style={{ padding: tokens.space[2], borderRadius: tokens.radius.md, background: tokens.color.bg, marginBottom: tokens.space[2] }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: tokens.space[1] }}>
              <span style={{ fontSize: tokens.font.sizeMd, fontWeight: 600, color: tokens.color.text }}>{exc.members?.name}</span>
              <Badge color="yellow">Pending</Badge>
            </div>
            <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>{exc.events?.title}</div>
            <div style={{ fontSize: tokens.font.sizeLg, color: tokens.color.text, fontStyle: "italic", margin: `${tokens.space[1]} 0 ${tokens.space[2]}` }}>&ldquo;{exc.reason}&rdquo;</div>
            <div style={{ display: "flex", gap: tokens.space[2] }}>
              <Btn variant="success" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => api.reviewExcuse(exc.id, "approved").then(onReload)}>Approve</Btn>
              <Btn variant="danger" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => api.reviewExcuse(exc.id, "denied").then(onReload)}>Deny</Btn>
            </div>
          </div>
        ))
      )}
    </Card>
  );
}

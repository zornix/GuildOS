"use client";
import { useState } from "react";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Toast } from "../components/ui/toast";
import { SegmentedControl } from "../components/ui/segmented-control";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import { formatMoney } from "../lib/formatters/money";
import type { Fine } from "../lib/types";

export function FinesPage() {
  const { user } = useAuth();
  const [filter, setFilter] = useState("all");
  const [toast, setToast] = useState<string | null>(null);
  const fines = useApi<Fine[]>(() => api.getFines());

  const show = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 2500);
  };

  const allData = fines.data || [];
  const filterOptions = [
    { value: "all", label: `all (${allData.length})` },
    { value: "unpaid", label: `unpaid (${allData.filter((x) => x.status === "unpaid").length})` },
    { value: "paid", label: `paid (${allData.filter((x) => x.status === "paid").length})` },
    { value: "waived", label: `waived (${allData.filter((x) => x.status === "waived").length})` },
  ];

  const filtered = allData.filter((f) => filter === "all" || f.status === filter);

  return (
    <div>
      <SegmentedControl options={filterOptions} value={filter} onChange={setFilter} />
      {fines.loading ? (
        <LoadingState />
      ) : filtered.length === 0 ? (
        <EmptyState message="No fines" />
      ) : (
        <div style={{ display: "grid", gap: tokens.space[2] }}>
          {filtered.map((f) => (
            <Card key={f.id} style={{ padding: tokens.space[4], display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                {user.role === "officer" && f.members && (
                  <div style={{ fontSize: tokens.font.sizeLg, fontWeight: tokens.font.weightBold, color: tokens.color.text }}>
                    {f.members.name}
                  </div>
                )}
                <div style={{ fontSize: tokens.font.sizeMd, color: tokens.color.text }}>{f.reason}</div>
                <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>{f.events?.title} · {f.events?.date}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
                <div style={{ fontSize: tokens.font.size2xl, fontWeight: tokens.font.weightExtrabold, color: f.status === "unpaid" ? tokens.color.danger : tokens.color.textMuted }}>
                  {formatMoney(f.amount)}
                </div>
                <Badge color={f.status === "paid" ? "green" : f.status === "waived" ? "blue" : "red"}>{f.status}</Badge>
                {f.status === "unpaid" && user.role === "officer" && (
                  <div style={{ display: "flex", gap: tokens.space[1], marginLeft: tokens.space[1] }}>
                    <Btn variant="ghost" style={{ padding: "4px 10px", fontSize: tokens.font.sizeSm }} onClick={() => api.waiveFine(f.id).then(() => { fines.reload(); show("Waived"); })}>Waive</Btn>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
      <Toast msg={toast} />
    </div>
  );
}

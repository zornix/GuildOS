"use client";
import { useState } from "react";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Toast } from "../components/ui/toast";
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

  const filtered = (fines.data || []).filter((f) => filter === "all" || f.status === filter);

  return (
    <div>
      <div style={{ display: "flex", gap: 4, background: T.sf, borderRadius: 8, padding: 3, marginBottom: 16, flexWrap: "wrap" }}>
        {["all", "unpaid", "paid", "waived"].map((f) => (
          <Btn
            key={f}
            variant={filter === f ? "primary" : "ghost"}
            style={{ textTransform: "capitalize", padding: "6px 12px", fontSize: 12 }}
            onClick={() => setFilter(f)}
          >
            {f} ({f === "all" ? (fines.data || []).length : (fines.data || []).filter((x) => x.status === f).length})
          </Btn>
        ))}
      </div>
      {fines.loading ? (
        <div style={{ color: T.txm, textAlign: "center", padding: 40 }}>Loading...</div>
      ) : filtered.length === 0 ? (
        <Card style={{ textAlign: "center", color: T.txm, padding: 40 }}>No fines</Card>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {filtered.map((f) => (
            <Card key={f.id} style={{ padding: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                {user.role === "officer" && f.members && <div style={{ fontSize: 14, fontWeight: 700, color: T.tx }}>{f.members.name}</div>}
                <div style={{ fontSize: 13, color: T.tx }}>{f.reason}</div>
                <div style={{ fontSize: 11, color: T.txm }}>{f.events?.title} · {f.events?.date}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: f.status === "unpaid" ? T.err : T.txm }}>${f.amount}</div>
                <Badge color={f.status === "paid" ? "green" : f.status === "waived" ? "blue" : "red"}>{f.status}</Badge>
                {f.status === "unpaid" && (
                  <div style={{ display: "flex", gap: 4, marginLeft: 4 }}>
                    <Btn variant="success" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => api.payFine(f.id).then(() => { fines.reload(); show("Paid"); })}>Pay</Btn>
                    {user.role === "officer" && (
                      <Btn variant="ghost" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => api.waiveFine(f.id).then(() => { fines.reload(); show("Waived"); })}>Waive</Btn>
                    )}
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

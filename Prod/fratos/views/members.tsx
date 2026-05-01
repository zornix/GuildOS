"use client";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Avatar } from "../components/ui/avatar";
import { ApiErrorBanner } from "../components/api-error-banner";
import type { Member } from "../lib/types";

export function MembersPage() {
  const { user } = useAuth();
  const members = useApi<Member[]>(() => api.getMembers());

  const toggleRole = async (m: Member) => {
    const newRole = m.role === "officer" ? "member" : "officer";
    await api.updateRole(m.id, newRole);
    members.reload();
  };

  return (
    <div>
      {members.error && (
        <ApiErrorBanner message={members.error} onRetry={members.reload} loading={members.loading} />
      )}
      <Card>
        <h3 style={{ margin: "0 0 14px", color: T.tx, fontSize: 16 }}>Chapter Roster</h3>
        {members.loading && !members.data?.length ? (
          <div style={{ color: T.txm, textAlign: "center", padding: 24 }}>Loading roster…</div>
        ) : members.error ? (
          <div style={{ color: T.txm, fontSize: 13, padding: 8 }}>Could not load members. Use Retry above.</div>
        ) : (members.data || []).length === 0 ? (
          <div style={{ color: T.txm, fontSize: 13, padding: 16, textAlign: "center" }}>No active members in this chapter.</div>
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {(members.data || []).map((m) => (
              <div key={m.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", borderRadius: 8, background: T.bg }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Avatar name={m.name} />
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>{m.name}</div>
                    <div style={{ fontSize: 11, color: T.txm }}>{m.email}</div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Badge color={m.role === "officer" ? "purple" : "gray"}>{m.role}</Badge>
                  {user.role === "officer" && m.id !== user.id && (
                    <Btn
                      variant="ghost"
                      style={{ padding: "4px 10px", fontSize: 11 }}
                      onClick={() => toggleRole(m)}
                    >
                      {m.role === "officer" ? "Demote" : "Promote"}
                    </Btn>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

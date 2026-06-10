"use client";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Avatar } from "../components/ui/avatar";
import { ListRow } from "../components/ui/list-row";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
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
        <h3 style={{ margin: "0 0 14px", color: tokens.color.text, fontSize: tokens.font.sizeXl }}>Chapter Roster</h3>
        {members.loading && !members.data?.length ? (
          <LoadingState message="Loading roster…" />
        ) : members.error ? (
          <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[2] }}>Could not load members. Use Retry above.</div>
        ) : (members.data || []).length === 0 ? (
          <EmptyState message="No active members in this chapter." />
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {(members.data || []).map((m) => (
              <ListRow
                key={m.id}
                left={<Avatar name={m.name} />}
                primary={m.name}
                secondary={m.email}
                right={
                  <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
                    <Badge color={m.role === "officer" ? "purple" : "gray"}>{m.role}</Badge>
                    {user.role === "officer" && m.id !== user.id && (
                      <Btn variant="ghost" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => toggleRole(m)}>
                        {m.role === "officer" ? "Demote" : "Promote"}
                      </Btn>
                    )}
                  </div>
                }
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

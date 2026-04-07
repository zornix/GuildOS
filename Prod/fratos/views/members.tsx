"use client";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Avatar } from "../components/ui/avatar";
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
      <Card>
        <h3 style={{ margin: "0 0 14px", color: T.tx, fontSize: 16 }}>Chapter Roster</h3>
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
      </Card>
    </div>
  );
}

"use client";
import { useState } from "react";
import { useApi } from "../hooks/use-api";
import { usePermissions } from "../hooks/use-permissions";
import { api } from "../lib/api-client";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Avatar } from "../components/ui/avatar";
import { ListRow } from "../components/ui/list-row";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import type { Member, MemberRole, RoleCatalogEntry } from "../lib/types";

function roleLabel(catalog: RoleCatalogEntry[], key: string): string {
  return catalog.find((r) => r.key === key)?.label ?? key;
}

export function AdminRolesPage() {
  const { can, loading: permsLoading, reload: reloadPermissions } = usePermissions();
  const canAssign = can("roles:assign");
  const members = useApi<Member[]>(() => (canAssign ? api.getMembers() : Promise.resolve([])), [canAssign]);
  const catalog = useApi<RoleCatalogEntry[]>(() => (canAssign ? api.getRoleCatalog() : Promise.resolve([])), [canAssign]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const memberRoles = useApi<MemberRole[]>(
    () => (canAssign && selectedId ? api.getMemberRoles(selectedId) : Promise.resolve([])),
    [canAssign, selectedId],
  );
  const [roleToAssign, setRoleToAssign] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  if (permsLoading) return <LoadingState />;
  if (!canAssign) {
    return (
      <Card style={{ textAlign: "center", color: tokens.color.textMuted, padding: tokens.space[8] }}>
        Role administration requires the roles:assign permission.
      </Card>
    );
  }

  const refreshAfterChange = async () => {
    await memberRoles.reload();
    // Changing your own roles changes what you can see.
    await reloadPermissions();
  };

  const assign = async () => {
    if (!selectedId || !roleToAssign) return;
    setActionError(null);
    try {
      await api.assignRole(selectedId, roleToAssign);
      setRoleToAssign("");
      await refreshAfterChange();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  const revoke = async (roleKey: string) => {
    if (!selectedId) return;
    setActionError(null);
    try {
      await api.revokeRole(selectedId, roleKey);
      await refreshAfterChange();
    } catch (e) {
      setActionError((e as Error).message);
    }
  };

  const memberList = members.data || [];
  const roleCatalog = catalog.data || [];
  const assigned = memberRoles.data || [];
  const assignedKeys = new Set(assigned.map((r) => r.role_key));
  const selected = memberList.find((m) => m.id === selectedId) ?? null;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 1fr) 2fr", gap: tokens.space[4], alignItems: "start" }}>
      <Card>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>Members</h3>
        {members.loading ? (
          <LoadingState />
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {memberList.map((m) => (
              <div key={m.id} onClick={() => setSelectedId(m.id)}>
                <ListRow
                  left={<Avatar name={m.name} />}
                  primary={m.name}
                  secondary={m.email}
                  right={selectedId === m.id ? <Badge color="purple">Selected</Badge> : undefined}
                  style={{ cursor: "pointer", outline: selectedId === m.id ? `1px solid ${tokens.color.accent}` : "none" }}
                />
              </div>
            ))}
            {memberList.length === 0 && <EmptyState message="No members found" />}
          </div>
        )}
      </Card>

      <Card>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, fontSize: 15 }}>
          {selected ? `Roles — ${selected.name}` : "Roles"}
        </h3>
        {actionError && (
          <div style={{ color: tokens.color.danger, fontSize: tokens.font.sizeSm, marginBottom: tokens.space[3] }}>{actionError}</div>
        )}
        {!selected ? (
          <EmptyState message="Select a member to manage their roles" />
        ) : memberRoles.loading ? (
          <LoadingState />
        ) : (
          <>
            <div style={{ display: "grid", gap: 6, marginBottom: tokens.space[4] }}>
              {assigned.map((r) => (
                <ListRow
                  key={r.id}
                  primary={roleLabel(roleCatalog, r.role_key)}
                  secondary={`Assigned ${new Date(r.assigned_at).toLocaleDateString()}`}
                  right={
                    <Btn variant="danger" style={{ padding: "4px 10px", fontSize: tokens.font.sizeSm }} onClick={() => revoke(r.role_key)}>
                      Revoke
                    </Btn>
                  }
                />
              ))}
              {assigned.length === 0 && <EmptyState message="No roles assigned" />}
            </div>
            <div style={{ display: "flex", gap: tokens.space[2], alignItems: "center" }}>
              <select
                value={roleToAssign}
                onChange={(e) => setRoleToAssign(e.target.value)}
                style={{
                  flex: 1,
                  padding: `${tokens.space[2]} ${tokens.space[3]}`,
                  borderRadius: tokens.radius.md,
                  border: `1px solid ${tokens.color.border}`,
                  background: tokens.color.bg,
                  color: tokens.color.text,
                  fontSize: tokens.font.sizeMd,
                }}
              >
                <option value="">Select a role…</option>
                {roleCatalog
                  .filter((r) => !assignedKeys.has(r.key))
                  .map((r) => (
                    <option key={r.key} value={r.key}>{r.label}</option>
                  ))}
              </select>
              <Btn onClick={assign} disabled={!roleToAssign}>Assign</Btn>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

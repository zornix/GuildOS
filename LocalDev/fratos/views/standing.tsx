"use client";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Avatar } from "../components/ui/avatar";
import { StatCard } from "../components/ui/stat-card";
import { ListRow } from "../components/ui/list-row";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import type { MemberStanding } from "../lib/types";

function standingBadge(standing: string) {
  if (standing === "good_standing") return <Badge color="green">Good Standing</Badge>;
  if (standing === "warning") return <Badge color="yellow">Warning</Badge>;
  return <Badge color="red">Delinquent</Badge>;
}

export function StandingPage() {
  const { user } = useAuth();
  const standings = useApi<MemberStanding[]>(
    () => (user.role === "officer" ? api.getStandings() : Promise.resolve([])),
    [user.role],
  );

  if (user.role !== "officer") {
    return (
      <Card style={{ textAlign: "center", color: tokens.color.textMuted, padding: tokens.space[7] }}>
        Officer access required to view member standing.
      </Card>
    );
  }

  const data = standings.data || [];
  const delinquent = data.filter((s) => s.standing === "delinquent").length;
  const warning = data.filter((s) => s.standing === "warning").length;

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: tokens.space[4], marginBottom: tokens.space[5] }}>
        <StatCard label="Delinquent" value={String(delinquent)} icon="alert" color={T.err} />
        <StatCard label="Warning" value={String(warning)} icon="alert" color={T.warn} />
        <StatCard label="Good Standing" value={String(data.length - delinquent - warning)} icon="check" color={T.ok} />
      </div>

      <Card>
        <div style={{ marginBottom: tokens.space[3] }}>
          <h3 style={{ margin: 0, color: tokens.color.text, fontSize: 15 }}>Member Standing</h3>
          <p style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeXs, margin: "4px 0 0" }}>
            Delinquent: 2+ unpaid fines or $50+ owed or 3+ unexcused absences.
            Warning: 1 unpaid fine or 1+ unexcused absence.
          </p>
        </div>

        {standings.loading ? (
          <LoadingState />
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {data.map((m) => (
              <ListRow
                key={m.member_id}
                left={<Avatar name={m.name} />}
                primary={m.name}
                secondary={`${m.attended}/${m.total_required} attended${m.unexcused_absences > 0 ? ` · ${m.unexcused_absences} unexcused` : ""}`}
                right={
                  <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
                    {m.unpaid_fines > 0 && (
                      <span style={{ fontSize: tokens.font.sizeXs, color: tokens.color.danger }}>${m.unpaid_amount} owed</span>
                    )}
                    {standingBadge(m.standing)}
                  </div>
                }
              />
            ))}
            {data.length === 0 && <EmptyState message="No members found" />}
          </div>
        )}
      </Card>
    </div>
  );
}

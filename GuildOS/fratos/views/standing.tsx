"use client";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Avatar } from "../components/ui/avatar";
import { Icon } from "../components/ui/icon";
import type { MemberStanding } from "../lib/types";

function standingBadge(standing: string) {
  if (standing === "good_standing") return <Badge color="green">Good Standing</Badge>;
  if (standing === "warning") return <Badge color="yellow">Warning</Badge>;
  return <Badge color="red">Delinquent</Badge>;
}

export function StandingPage() {
  const { user } = useAuth();
  const standings = useApi<MemberStanding[]>(() => api.getStandings());

  if (user.role !== "officer") {
    return (
      <Card style={{ textAlign: "center", color: T.txm, padding: 40 }}>
        Officer access required to view member standing.
      </Card>
    );
  }

  const data = standings.data || [];
  const delinquent = data.filter((s) => s.standing === "delinquent").length;
  const warning = data.filter((s) => s.standing === "warning").length;

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 20 }}>
        <Card style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 10, background: T.err + "22", display: "flex", alignItems: "center", justifyContent: "center", color: T.err }}>
            <Icon type="alert" />
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: T.tx }}>{delinquent}</div>
            <div style={{ fontSize: 11, color: T.txm }}>Delinquent</div>
          </div>
        </Card>
        <Card style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 10, background: T.warn + "22", display: "flex", alignItems: "center", justifyContent: "center", color: T.warn }}>
            <Icon type="alert" />
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: T.tx }}>{warning}</div>
            <div style={{ fontSize: 11, color: T.txm }}>Warning</div>
          </div>
        </Card>
        <Card style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 10, background: T.ok + "22", display: "flex", alignItems: "center", justifyContent: "center", color: T.ok }}>
            <Icon type="check" />
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: T.tx }}>{data.length - delinquent - warning}</div>
            <div style={{ fontSize: 11, color: T.txm }}>Good Standing</div>
          </div>
        </Card>
      </div>

      <Card>
        <div style={{ marginBottom: 10 }}>
          <h3 style={{ margin: 0, color: T.tx, fontSize: 15 }}>Member Standing</h3>
          <p style={{ color: T.txm, fontSize: 11, margin: "4px 0 0" }}>
            Delinquent: 2+ unpaid fines or $50+ owed or 3+ unexcused absences.
            Warning: 1 unpaid fine or 1+ unexcused absence.
          </p>
        </div>

        {standings.loading ? (
          <div style={{ color: T.txm, textAlign: "center", padding: 40 }}>Loading...</div>
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {data.map((m) => (
              <div
                key={m.member_id}
                style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", borderRadius: 8, background: T.bg }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
                  <Avatar name={m.name} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>{m.name}</div>
                    <div style={{ fontSize: 11, color: T.txm }}>
                      {m.attended}/{m.total_required} attended
                      {m.unexcused_absences > 0 && ` · ${m.unexcused_absences} unexcused`}
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {m.unpaid_fines > 0 && (
                    <span style={{ fontSize: 11, color: T.err }}>${m.unpaid_amount} owed</span>
                  )}
                  {standingBadge(m.standing)}
                </div>
              </div>
            ))}
            {data.length === 0 && (
              <div style={{ color: T.txm, fontSize: 13, textAlign: "center", padding: 20 }}>No members found</div>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

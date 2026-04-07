"use client";
import { useState } from "react";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Icon } from "../components/ui/icon";
import { Avatar } from "../components/ui/avatar";
import { Modal } from "../components/ui/modal";
import { Toast } from "../components/ui/toast";
import type { DelinquencyScore, MemberDelinquencyDetail, SecurityAssignment } from "../lib/types";

function ScoreBar({ score }: { score: number }) {
  const color = score >= 80 ? T.ok : score >= 50 ? T.warn : T.err;
  return (
    <div style={{ width: 80, height: 6, borderRadius: 3, background: T.bg, overflow: "hidden" }}>
      <div style={{ width: `${score}%`, height: "100%", borderRadius: 3, background: color, transition: "width 0.3s" }} />
    </div>
  );
}

function scoreBadge(score: number) {
  if (score >= 80) return <Badge color="green">Good</Badge>;
  if (score >= 50) return <Badge color="yellow">At Risk</Badge>;
  return <Badge color="red">Delinquent</Badge>;
}

function MemberDetail({ memberId, onBack }: { memberId: string; onBack: () => void }) {
  const detail = useApi<MemberDelinquencyDetail>(() => api.getMemberDelinquency(memberId), [memberId]);
  const [toast, setToast] = useState<string | null>(null);

  const statusBadge = (status: string) => {
    switch (status) {
      case "present": return <Badge color="green">Present</Badge>;
      case "excused": return <Badge color="blue">Excused</Badge>;
      case "excuse_pending": return <Badge color="yellow">Pending</Badge>;
      case "absent": return <Badge color="red">Absent</Badge>;
      default: return null;
    }
  };

  const handleReminder = async () => {
    const res = await api.sendReminder(memberId);
    setToast(`Reminder sent to ${res.sent_to} ($${res.unpaid_total} unpaid)`);
    setTimeout(() => setToast(null), 3000);
  };

  if (detail.loading) return <div style={{ color: T.txm, textAlign: "center", padding: 40 }}>Loading...</div>;
  if (!detail.data) return null;

  const { member, breakdown } = detail.data;

  return (
    <div>
      <button onClick={onBack} style={{ background: "none", border: "none", color: T.acl, cursor: "pointer", fontSize: 13, marginBottom: 16, padding: 0 }}>
        ← Back to Scores
      </button>

      <Card style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Avatar name={member.name} size={40} />
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: T.tx }}>{member.name}</div>
              <div style={{ fontSize: 12, color: T.txm }}>{member.email}</div>
            </div>
          </div>
          <Btn variant="ghost" onClick={handleReminder}>
            <Icon type="bell" size={14} /> Send Reminder
          </Btn>
        </div>
      </Card>

      <Card>
        <h3 style={{ margin: "0 0 12px", color: T.tx, fontSize: 15 }}>Required Event History</h3>
        <div style={{ display: "grid", gap: 6 }}>
          {breakdown.map((ev) => (
            <div key={ev.event_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", borderRadius: 8, background: T.bg }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>{ev.event_title}</div>
                <div style={{ fontSize: 11, color: T.txm }}>{ev.event_date}</div>
              </div>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {ev.fine_amount != null && (
                  <span style={{ fontSize: 11, color: ev.fine_status === "unpaid" ? T.err : T.txm }}>
                    ${ev.fine_amount} {ev.fine_status}
                  </span>
                )}
                {statusBadge(ev.status)}
              </div>
            </div>
          ))}
          {breakdown.length === 0 && (
            <div style={{ color: T.txm, fontSize: 13, textAlign: "center", padding: 20 }}>No required events yet</div>
          )}
        </div>
      </Card>
      <Toast msg={toast} />
    </div>
  );
}

export function DelinquencyPage() {
  const { user } = useAuth();
  const scores = useApi<DelinquencyScore[]>(() => api.getDelinquencyScores());
  const [selectedMember, setSelectedMember] = useState<string | null>(null);
  const [securityModal, setSecurityModal] = useState(false);
  const [securityPicks, setSecurityPicks] = useState<SecurityAssignment | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  if (user.role !== "officer") {
    return (
      <Card style={{ textAlign: "center", color: T.txm, padding: 40 }}>
        Officer access required to view delinquency tracking.
      </Card>
    );
  }

  if (selectedMember) {
    return <MemberDetail memberId={selectedMember} onBack={() => setSelectedMember(null)} />;
  }

  const handleAssignSecurity = async () => {
    const result = await api.assignSecurity();
    setSecurityPicks(result);
    setSecurityModal(true);
  };

  const handleReminder = async (memberId: string, name: string) => {
    await api.sendReminder(memberId);
    setToast(`Reminder sent to ${name}`);
    setTimeout(() => setToast(null), 2500);
  };

  const data = scores.data || [];
  const atRisk = data.filter((s) => s.score < 80);

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 20 }}>
        <Card style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 10, background: T.err + "22", display: "flex", alignItems: "center", justifyContent: "center", color: T.err }}>
            <Icon type="alert" />
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: T.tx }}>{atRisk.length}</div>
            <div style={{ fontSize: 11, color: T.txm }}>At Risk / Delinquent</div>
          </div>
        </Card>
        <Card style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 42, height: 42, borderRadius: 10, background: T.warn + "22", display: "flex", alignItems: "center", justifyContent: "center", color: T.warn }}>
            <Icon type="dollar" />
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 700, color: T.tx }}>
              ${data.reduce((s, d) => s + d.unpaid_amount, 0)}
            </div>
            <div style={{ fontSize: 11, color: T.txm }}>Total Unpaid</div>
          </div>
        </Card>
        <Card style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Btn onClick={handleAssignSecurity}>
            <Icon type="shield" size={14} /> Auto-Pick Security
          </Btn>
        </Card>
      </div>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h3 style={{ margin: 0, color: T.tx, fontSize: 15 }}>Member Engagement Scores</h3>
          <span style={{ fontSize: 11, color: T.txm }}>Sorted: most delinquent first</span>
        </div>

        {scores.loading ? (
          <div style={{ color: T.txm, textAlign: "center", padding: 40 }}>Loading...</div>
        ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {data.map((m) => (
              <div
                key={m.member_id}
                onClick={() => setSelectedMember(m.member_id)}
                style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 12px", borderRadius: 8, background: T.bg, cursor: "pointer" }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
                  <Avatar name={m.name} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>{m.name}</div>
                    <div style={{ fontSize: 11, color: T.txm }}>
                      {m.attended}/{m.total_required} attended · {m.excused} excused · {m.missed} missed
                    </div>
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  {m.unpaid_fines > 0 && (
                    <span style={{ fontSize: 11, color: T.err }}>${m.unpaid_amount} owed</span>
                  )}
                  <ScoreBar score={m.score} />
                  <span style={{ fontSize: 14, fontWeight: 700, color: T.tx, width: 36, textAlign: "right" }}>{m.score}</span>
                  {scoreBadge(m.score)}
                  <Btn
                    variant="ghost"
                    style={{ padding: "4px 8px", fontSize: 10 }}
                    onClick={(e: React.MouseEvent) => { e.stopPropagation(); handleReminder(m.member_id, m.name); }}
                  >
                    Remind
                  </Btn>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {securityModal && securityPicks && (
        <Modal onClose={() => setSecurityModal(false)}>
          <h3 style={{ margin: "0 0 4px", color: T.tx, fontSize: 17 }}>Security Assignments</h3>
          <p style={{ color: T.txm, fontSize: 13, margin: "0 0 16px" }}>
            Auto-selected from lowest engagement scores
          </p>
          <div style={{ display: "grid", gap: 8 }}>
            {securityPicks.assigned.map((p, i) => (
              <div key={p.member_id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", borderRadius: 8, background: T.bg }}>
                <div style={{ width: 24, height: 24, borderRadius: "50%", background: T.err + "33", color: T.err, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 700 }}>
                  {i + 1}
                </div>
                <Avatar name={p.name} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>{p.name}</div>
                </div>
                <span style={{ fontSize: 13, fontWeight: 600, color: T.txm }}>Score: {p.score}</span>
              </div>
            ))}
          </div>
          <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
            <Btn onClick={() => setSecurityModal(false)}>Done</Btn>
          </div>
        </Modal>
      )}

      <Toast msg={toast} />
    </div>
  );
}

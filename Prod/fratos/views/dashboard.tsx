"use client";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Icon } from "../components/ui/icon";
import type { Event, Fine, Excuse } from "../lib/types";

export function DashboardPage() {
  const { user } = useAuth();
  const events = useApi<Event[]>(() => api.getEvents());
  const fines = useApi<Fine[]>(() => api.getFines());
  const excuses = useApi<Excuse[]>(() => api.getExcuses(user.role === "officer" ? "pending" : null));

  const now = new Date();
  const upcoming = (events.data || []).filter((e) => new Date(e.date) >= now);
  const pendingExcuses = (excuses.data || []).filter((e) => e.status === "pending");
  const unpaidFines = (fines.data || []).filter((f) => f.status === "unpaid");

  const stats =
    user.role === "officer"
      ? [
          { label: "Upcoming Events", value: upcoming.length, icon: "cal", color: T.ac },
          { label: "Pending Excuses", value: pendingExcuses.length, icon: "file", color: T.warn },
          { label: "Unpaid Fines", value: `$${unpaidFines.reduce((s, f) => s + f.amount, 0)}`, icon: "dollar", color: T.err },
        ]
      : [
          { label: "Upcoming Events", value: upcoming.length, icon: "cal", color: T.ac },
          { label: "My Unpaid Fines", value: unpaidFines.length, icon: "dollar", color: T.err },
        ];

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${stats.length}, 1fr)`, gap: 16, marginBottom: 24 }}>
        {stats.map((s, i) => (
          <Card key={i} style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ width: 42, height: 42, borderRadius: 10, background: s.color + "22", display: "flex", alignItems: "center", justifyContent: "center", color: s.color }}>
              <Icon type={s.icon} />
            </div>
            <div>
              <div style={{ fontSize: 22, fontWeight: 700, color: T.tx }}>{s.value}</div>
              <div style={{ fontSize: 11, color: T.txm }}>{s.label}</div>
            </div>
          </Card>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card>
          <div style={{ fontSize: 15, fontWeight: 700, color: T.tx, marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
            <Icon type="cal" /> Upcoming
          </div>
          {upcoming.length === 0 ? (
            <div style={{ color: T.txm, fontSize: 13, padding: 16, textAlign: "center" }}>No upcoming events</div>
          ) : (
            upcoming.slice(0, 5).map((e) => (
              <div key={e.id} style={{ padding: "10px 12px", borderRadius: 8, background: T.bg, marginBottom: 6, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>{e.title}</div>
                  <div style={{ fontSize: 11, color: T.txm }}>{e.date} · {e.time}</div>
                </div>
                {e.required && <Badge color="purple">Required</Badge>}
              </div>
            ))
          )}
        </Card>
        <Card>
          <div style={{ fontSize: 15, fontWeight: 700, color: T.tx, marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
            {user.role === "officer" ? (
              <><Icon type="file" /> Pending Excuses</>
            ) : (
              <><Icon type="dollar" /> My Fines</>
            )}
          </div>
          {user.role === "officer" ? (
            pendingExcuses.length === 0 ? (
              <div style={{ color: T.txm, fontSize: 13, padding: 16, textAlign: "center" }}>All clear</div>
            ) : (
              pendingExcuses.slice(0, 5).map((exc) => (
                <div key={exc.id} style={{ padding: 10, borderRadius: 8, background: T.bg, marginBottom: 6 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>{exc.members?.name}</span>
                    <Badge color="yellow">Pending</Badge>
                  </div>
                  <div style={{ fontSize: 11, color: T.txm }}>{exc.events?.title}</div>
                  <div style={{ fontSize: 12, color: T.tx, fontStyle: "italic", margin: "4px 0 8px" }}>&ldquo;{exc.reason}&rdquo;</div>
                  <div style={{ display: "flex", gap: 6 }}>
                    <Btn variant="success" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => api.reviewExcuse(exc.id, "approved").then(excuses.reload)}>Approve</Btn>
                    <Btn variant="danger" style={{ padding: "4px 10px", fontSize: 11 }} onClick={() => api.reviewExcuse(exc.id, "denied").then(excuses.reload)}>Deny</Btn>
                  </div>
                </div>
              ))
            )
          ) : unpaidFines.length === 0 ? (
            <div style={{ color: T.txm, fontSize: 13, padding: 16, textAlign: "center" }}>No fines — keep it up!</div>
          ) : (
            unpaidFines.map((f) => (
              <div key={f.id} style={{ padding: 10, borderRadius: 8, background: T.bg, marginBottom: 6, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>${f.amount}</div>
                  <div style={{ fontSize: 11, color: T.txm }}>{f.reason}</div>
                </div>
                <Badge color="red">Unpaid</Badge>
              </div>
            ))
          )}
        </Card>
      </div>
    </div>
  );
}

"use client";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Countdown } from "../components/countdown";
import type { ActiveCheckinLinkRow } from "../lib/types";

export function ActiveCheckInsPage() {
  const links = useApi<ActiveCheckinLinkRow[]>(() => api.listActiveCheckinLinks());

  if (links.loading) {
    return <div style={{ color: T.txm, textAlign: "center", padding: 40 }}>Loading...</div>;
  }

  if (!links.data?.length) {
    return <Card style={{ textAlign: "center", color: T.txm, padding: 40 }}>No active check-in links</Card>;
  }

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {links.data.map((link) => (
        <Card key={link.short_code} style={{ padding: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.tx }}>{link.event_title}</div>
              <div style={{ fontSize: 12, color: T.txm, marginTop: 2 }}>{link.date}</div>
            </div>
            <Badge color="green">Active</Badge>
          </div>
          <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
            <div style={{ fontFamily: "monospace", fontSize: 22, fontWeight: 800, color: T.tx, letterSpacing: 3, background: T.bg, padding: "6px 16px", borderRadius: 8 }}>
              /c/{link.short_code}
            </div>
            <div style={{ fontSize: 12, color: T.txm }}>
              <span style={{ color: T.acl, fontFamily: "monospace" }}>{link.url}</span>
            </div>
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 12, color: T.txm }}>Expires in:</span>
              <Countdown expiresAt={link.expires_at} />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

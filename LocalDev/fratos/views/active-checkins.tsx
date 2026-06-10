"use client";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { tokens } from "../config/theme/tokens";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { LoadingState } from "../components/ui/loading-state";
import { EmptyState } from "../components/ui/empty-state";
import { Countdown } from "../components/countdown";
import type { ActiveCheckinLinkRow } from "../lib/types";

export function ActiveCheckInsPage() {
  const links = useApi<ActiveCheckinLinkRow[]>(() => api.listActiveCheckinLinks());

  if (links.loading) {
    return <LoadingState />;
  }

  if (!links.data?.length) {
    return <EmptyState message="No active check-in links" />;
  }

  return (
    <div style={{ display: "grid", gap: tokens.space[3] }}>
      {links.data.map((link) => (
        <Card key={link.short_code} style={{ padding: tokens.space[4] }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: tokens.space[3] }}>
            <div>
              <div style={{ fontSize: tokens.font.sizeLg, fontWeight: tokens.font.weightBold, color: tokens.color.text }}>{link.event_title}</div>
              <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, marginTop: 2 }}>{link.date}</div>
            </div>
            <Badge color="green">Active</Badge>
          </div>
          <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: tokens.space[4], flexWrap: "wrap" }}>
            <div style={{ fontFamily: "monospace", fontSize: tokens.font.size2xl, fontWeight: tokens.font.weightExtrabold, color: tokens.color.text, letterSpacing: 3, background: tokens.color.bg, padding: "6px 16px", borderRadius: tokens.radius.md }}>
              /c/{link.short_code}
            </div>
            <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>
              <span style={{ color: T.acl, fontFamily: "monospace" }}>{link.url}</span>
            </div>
            <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>Expires in:</span>
              <Countdown expiresAt={link.expires_at} />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

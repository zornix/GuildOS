"use client";
import { tokens } from "../../../config/theme/tokens";
import { Card } from "../../ui/card";
import { Countdown } from "../../countdown";
import { T } from "../../../lib/theme";
import type { CheckinLink } from "../../../lib/types";

interface CheckinCodeCardProps {
  link: CheckinLink;
}

export function CheckinCodeCard({ link }: CheckinCodeCardProps) {
  return (
    <Card style={{ marginBottom: tokens.space[4], textAlign: "center", background: `linear-gradient(135deg, ${T.ac}15, ${tokens.color.surface})` }}>
      <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: tokens.space[2] }}>
        Check-In Link Active
      </div>
      <div style={{ fontFamily: "monospace", fontSize: 28, fontWeight: 800, color: tokens.color.text, letterSpacing: 4, margin: "8px 0", background: tokens.color.bg, display: "inline-block", padding: "10px 24px", borderRadius: tokens.radius.lg }}>
        /c/{link.short_code}
      </div>
      <div style={{ marginTop: tokens.space[2], fontSize: tokens.font.sizeMd, color: tokens.color.textMuted }}>
        Full link: <span style={{ color: tokens.color.accentMuted, fontFamily: "monospace" }}>{link.url || `fraternityos.vercel.app/c/${link.short_code}`}</span>
      </div>
      <div style={{ marginTop: tokens.space[3] }}>
        <span style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, marginRight: tokens.space[2] }}>Expires in:</span>
        <Countdown expiresAt={link.expires_at} />
      </div>
    </Card>
  );
}

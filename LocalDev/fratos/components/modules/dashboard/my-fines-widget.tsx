"use client";
import { tokens } from "../../../config/theme/tokens";
import { Card } from "../../ui/card";
import { Icon } from "../../ui/icon";
import { Badge } from "../../ui/badge";
import { formatMoney } from "../../../lib/formatters/money";
import type { Fine } from "../../../lib/contracts/fines";

interface MyFinesWidgetProps {
  fines: Fine[] | null;
  loading: boolean;
  error: string | null;
}

export function MyFinesWidget({ fines, loading, error }: MyFinesWidgetProps) {
  const unpaid = (fines || []).filter((f) => f.status === "unpaid");

  return (
    <Card>
      <div style={{ fontSize: tokens.font.sizeXl, fontWeight: tokens.font.weightBold, color: tokens.color.text, marginBottom: 14, display: "flex", alignItems: "center", gap: tokens.space[2] }}>
        <Icon type="dollar" /> My Fines
      </div>
      {loading && !unpaid.length ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>Loading fines…</div>
      ) : error ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>Could not load fines. Use Retry above.</div>
      ) : unpaid.length === 0 ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>No fines — keep it up!</div>
      ) : (
        unpaid.map((f) => (
          <div key={f.id} style={{ padding: tokens.space[2], borderRadius: tokens.radius.md, background: tokens.color.bg, marginBottom: tokens.space[2], display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: tokens.font.sizeMd, fontWeight: 600, color: tokens.color.text }}>{formatMoney(f.amountCents)}</div>
              <div style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted }}>{f.reason}</div>
            </div>
            <Badge color="red">Unpaid</Badge>
          </div>
        ))
      )}
    </Card>
  );
}

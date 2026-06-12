"use client";
import { Badge } from "../ui/badge";
import { tokens } from "../../config/theme/tokens";
import { NAV, type PageId } from "../../config/navigation";
import type { Member } from "../../lib/types";

interface PageHeaderProps {
  activePage: PageId;
  user: Member;
}

export function PageHeader({ activePage, user }: PageHeaderProps) {
  const label = NAV.find((n) => n.id === activePage)?.label ?? "";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: tokens.space[3], flexWrap: "wrap", marginBottom: tokens.space[5] }}>
      <h1 style={{ margin: 0, fontSize: tokens.font.size3xl, fontWeight: 800 }}>{label}</h1>
      <Badge color={user.role === "officer" ? "purple" : "blue"}>{user.role}</Badge>
    </div>
  );
}

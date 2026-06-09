"use client";
import { T } from "../../lib/theme";
import { tokens } from "../../config/theme/tokens";
import { Icon } from "../ui/icon";
import { UserMenu } from "./user-menu";
import { NAV, OFFICER_ONLY, type PageId, type NavItem } from "../../config/navigation";
import type { Member } from "../../lib/types";

interface SidebarProps {
  user: Member;
  activePage: PageId;
  onNavigate: (page: PageId) => void;
  onLogout: () => void;
}

export function Sidebar({ user, activePage, onNavigate, onLogout }: SidebarProps) {
  const navItems: NavItem[] = NAV.filter((n) => !OFFICER_ONLY.includes(n.id) || user.role === "officer");

  return (
    <div style={{
      width: tokens.layout.sidebarWidth,
      background: tokens.color.surface,
      borderRight: `1px solid ${tokens.color.border}`,
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
    }}>
      <div style={{ padding: `${tokens.space[5]} ${tokens.space[4]}`, borderBottom: `1px solid ${tokens.color.border}` }}>
        <div style={{ fontSize: 18, fontWeight: 800 }}>
          <span style={{ color: tokens.color.accent }}>Fraternity</span>OS
        </div>
        <div style={{ fontSize: 10, color: tokens.color.textMuted, marginTop: 2, textTransform: "uppercase", letterSpacing: 1 }}>
          Operations Platform
        </div>
      </div>
      <nav style={{ flex: 1, padding: `${tokens.space[3]} ${tokens.space[2]}` }}>
        {navItems.map((n) => (
          <button
            key={n.id}
            onClick={() => onNavigate(n.id)}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "10px 12px",
              borderRadius: tokens.radius.md,
              border: "none",
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 500,
              marginBottom: 2,
              background: activePage === n.id ? T.ac + "22" : "transparent",
              color: activePage === n.id ? tokens.color.accentMuted : tokens.color.textMuted,
            }}
          >
            <Icon type={n.icon} size={16} /> {n.label}
          </button>
        ))}
      </nav>
      <UserMenu user={user} onLogout={onLogout} />
    </div>
  );
}

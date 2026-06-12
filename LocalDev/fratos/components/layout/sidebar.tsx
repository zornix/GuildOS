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
  compact?: boolean;
  /** RBAC check for NavItem.requiredPermission; defaults to permissive so the shell can render before permissions load. */
  can?: (permission?: string) => boolean;
}

function NavButton({ item, active, onNavigate, compact = false }: { item: NavItem; active: boolean; onNavigate: (page: PageId) => void; compact?: boolean }) {
  return (
    <button
      onClick={() => onNavigate(item.id)}
      style={{
        width: compact ? "auto" : "100%",
        flex: compact ? "0 0 auto" : undefined,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 12px",
        borderRadius: tokens.radius.md,
        border: "none",
        cursor: "pointer",
        fontSize: 13,
        fontWeight: 500,
        marginBottom: compact ? 0 : 2,
        background: active ? T.ac + "22" : "transparent",
        color: active ? tokens.color.accentMuted : tokens.color.textMuted,
        whiteSpace: "nowrap",
      }}
    >
      <Icon type={item.icon} size={16} /> {item.label}
    </button>
  );
}

export function Sidebar({ user, activePage, onNavigate, onLogout, compact = false, can = () => true }: SidebarProps) {
  const navItems: NavItem[] = NAV.filter(
    (n) => (!OFFICER_ONLY.includes(n.id) || user.role === "officer") && can(n.requiredPermission),
  );

  if (compact) {
    return (
      <div
        style={{
          width: "100%",
          background: tokens.color.surface,
          borderBottom: `1px solid ${tokens.color.border}`,
          flexShrink: 0,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: tokens.space[3], padding: `${tokens.space[3]} ${tokens.space[4]}` }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 18, fontWeight: 800, whiteSpace: "nowrap" }}>
              <span style={{ color: tokens.color.accent }}>Fraternity</span>OS
            </div>
            <div style={{ fontSize: 10, color: tokens.color.textMuted, marginTop: 2, textTransform: "uppercase", letterSpacing: 1 }}>
              Operations Platform
            </div>
          </div>
          <button
            onClick={onLogout}
            style={{
              minWidth: 0,
              display: "inline-flex",
              alignItems: "center",
              gap: tokens.space[2],
              background: "none",
              border: "none",
              color: tokens.color.textMuted,
              cursor: "pointer",
              padding: tokens.space[2],
            }}
            title="Sign out"
          >
            <span style={{ maxWidth: 108, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontSize: 12, color: tokens.color.text }}>
              {user.name}
            </span>
            <Icon type="out" size={14} />
          </button>
        </div>
        <nav style={{ display: "flex", gap: tokens.space[2], overflowX: "auto", padding: `0 ${tokens.space[3]} ${tokens.space[3]}` }}>
          {navItems.map((item) => (
            <NavButton key={item.id} item={item} active={activePage === item.id} onNavigate={onNavigate} compact />
          ))}
        </nav>
      </div>
    );
  }

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
        {navItems.map((item) => (
          <NavButton key={item.id} item={item} active={activePage === item.id} onNavigate={onNavigate} />
        ))}
      </nav>
      <UserMenu user={user} onLogout={onLogout} />
    </div>
  );
}

"use client";
import { Avatar } from "../ui/avatar";
import { Icon } from "../ui/icon";
import { tokens } from "../../config/theme/tokens";
import type { Member } from "../../lib/types";

interface UserMenuProps {
  user: Member;
  onLogout: () => void;
}

export function UserMenu({ user, onLogout }: UserMenuProps) {
  return (
    <div style={{ padding: tokens.space[3], borderTop: `1px solid ${tokens.color.border}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 4px" }}>
        <Avatar name={user.name} size={28} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: tokens.color.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{user.name}</div>
          <div style={{ fontSize: 10, color: tokens.color.textMuted, textTransform: "capitalize" }}>{user.role}</div>
        </div>
        <button onClick={onLogout} style={{ background: "none", border: "none", color: tokens.color.textMuted, cursor: "pointer", padding: 4 }} title="Sign out">
          <Icon type="out" size={14} />
        </button>
      </div>
    </div>
  );
}

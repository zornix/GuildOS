"use client";
import { tokens } from "../../../config/theme/tokens";
import { Avatar } from "../../ui/avatar";
import { Badge } from "../../ui/badge";
import { Btn } from "../../ui/btn";
import type { RosterEntry } from "../../../lib/types";

interface AttendanceRowProps {
  entry: RosterEntry;
  isOfficer: boolean;
  onSetStatus: () => void;
}

export function AttendanceRow({ entry: m, isOfficer, onSetStatus }: AttendanceRowProps) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", borderRadius: tokens.radius.md, background: tokens.color.bg }}>
      <div style={{ display: "flex", alignItems: "center", gap: tokens.space[2] }}>
        <Avatar name={m.name} />
        <div>
          <div style={{ fontSize: tokens.font.sizeMd, fontWeight: 600, color: tokens.color.text }}>{m.name}</div>
          {m.checked_in_at && (
            <div style={{ fontSize: tokens.font.sizeXs, color: tokens.color.textMuted }}>
              {new Date(m.checked_in_at).toLocaleTimeString()} · {m.method}
            </div>
          )}
        </div>
      </div>
      <div style={{ display: "flex", gap: tokens.space[2], alignItems: "center" }}>
        {m.checked_in ? (
          <Badge color="green">Present</Badge>
        ) : m.excuse_status === "approved" ? (
          <Badge color="blue">Excused</Badge>
        ) : m.excuse_status ? (
          <Badge color={m.excuse_status === "denied" ? "red" : "yellow"}>{m.excuse_status}</Badge>
        ) : (
          <Badge color="red">Absent</Badge>
        )}
        {isOfficer && (
          <Btn variant="ghost" style={{ padding: "2px 8px", fontSize: 10 }} onClick={onSetStatus}>
            Set Status
          </Btn>
        )}
      </div>
    </div>
  );
}

"use client";
import { tokens } from "../../../config/theme/tokens";
import { Card } from "../../ui/card";
import { Btn } from "../../ui/btn";
import { Icon } from "../../ui/icon";
import { LoadingState } from "../../ui/loading-state";
import { ApiErrorBanner } from "../../api-error-banner";
import { AttendanceRow } from "./attendance-row";
import type { RosterEntry } from "../../../lib/types";

interface AttendanceRosterProps {
  attendance: RosterEntry[];
  loading: boolean;
  error: string | null;
  isOfficer: boolean;
  isPast: boolean;
  required: boolean;
  fineAmount: number;
  onRetry: () => void;
  onSetStatus: (target: { eventId: string; memberId: string; name: string }) => void;
  onProcessFines: () => void;
  eventId: string;
}

export function AttendanceRoster({ attendance, loading, error, isOfficer, isPast, required, fineAmount, onRetry, onSetStatus, onProcessFines, eventId }: AttendanceRosterProps) {
  const checkedIn = attendance.filter((a) => a.checked_in).length;

  return (
    <Card>
      {error && (
        <ApiErrorBanner message={error} onRetry={onRetry} loading={loading} />
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: tokens.space[2], marginBottom: tokens.space[3] }}>
        <h3 style={{ margin: 0, color: tokens.color.text, fontSize: 15 }}>
          Attendance ({checkedIn}/{attendance.length})
        </h3>
        {isOfficer && isPast && required && fineAmount > 0 && (
          <Btn variant="danger" style={{ padding: "6px 12px", fontSize: 12 }} onClick={onProcessFines}>
            <Icon type="dollar" size={14} /> Fine unexcused absences
          </Btn>
        )}
      </div>
      {loading && !attendance.length ? (
        <LoadingState message="Loading attendance…" />
      ) : error && !attendance.length ? (
        <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, padding: tokens.space[4], textAlign: "center" }}>
          Could not load attendance. Use Retry above.
        </div>
      ) : (
        <div style={{ display: "grid", gap: 6 }}>
          {attendance.map((m) => (
            <AttendanceRow
              key={m.member_id}
              entry={m}
              isOfficer={isOfficer}
              onSetStatus={() => onSetStatus({ eventId, memberId: m.member_id, name: m.name })}
            />
          ))}
        </div>
      )}
    </Card>
  );
}

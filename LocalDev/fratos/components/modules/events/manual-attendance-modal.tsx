"use client";
import { tokens } from "../../../config/theme/tokens";
import { Modal } from "../../ui/modal";
import { Card } from "../../ui/card";
import { Btn } from "../../ui/btn";
import { Textarea } from "../../ui/textarea";

type AttendanceStatus = "present" | "excused" | "absent";

interface ManualAttendanceModalProps {
  target: { eventId: string; memberId: string; name: string };
  status: AttendanceStatus;
  reason: string;
  onStatusChange: (s: AttendanceStatus) => void;
  onReasonChange: (r: string) => void;
  onConfirm: () => void;
  onClose: () => void;
}

export function ManualAttendanceModal({ target, status, reason, onStatusChange, onReasonChange, onConfirm, onClose }: ManualAttendanceModalProps) {
  return (
    <Modal onClose={onClose}>
      <Card style={{ maxWidth: 400, margin: "0 auto" }}>
        <h3 style={{ margin: `0 0 ${tokens.space[3]}`, color: tokens.color.text, fontSize: 16 }}>
          Set Attendance — {target.name}
        </h3>
        <div style={{ display: "flex", gap: tokens.space[2], marginBottom: tokens.space[4] }}>
          {(["present", "excused", "absent"] as const).map((s) => (
            <Btn key={s} variant={status === s ? "primary" : "ghost"} style={{ textTransform: "capitalize", padding: "6px 14px", flex: 1 }} onClick={() => onStatusChange(s)}>
              {s}
            </Btn>
          ))}
        </div>
        {status === "excused" && (
          <div style={{ marginBottom: tokens.space[4] }}>
            <label style={{ fontSize: tokens.font.sizeSm, color: tokens.color.textMuted, display: "block", marginBottom: tokens.space[1] }}>
              Excuse reason (required)
            </label>
            <Textarea
              value={reason}
              onChange={(e) => onReasonChange(e.target.value)}
              placeholder="Enter excuse reason..."
              style={{ minHeight: 70 }}
            />
          </div>
        )}
        <div style={{ display: "flex", gap: tokens.space[2], justifyContent: "flex-end" }}>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn onClick={onConfirm}>Confirm</Btn>
        </div>
      </Card>
    </Modal>
  );
}

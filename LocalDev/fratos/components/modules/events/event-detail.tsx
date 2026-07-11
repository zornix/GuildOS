"use client";
import { tokens } from "../../../config/theme/tokens";
import { Card } from "../../ui/card";
import { Badge } from "../../ui/badge";
import { Btn } from "../../ui/btn";
import { Icon } from "../../ui/icon";
import { Modal } from "../../ui/modal";
import { ApiErrorBanner } from "../../api-error-banner";
import { CheckInForm } from "../../forms/check-in-form";
import { ExcuseForm } from "../../forms/excuse-form";
import { CheckinCodeCard } from "./checkin-code-card";
import { AttendanceRoster } from "./attendance-roster";
import { ManualAttendanceModal } from "./manual-attendance-modal";
import type { Event, RosterEntry, CheckinLink } from "../../../lib/types";
import { isPastEvent } from "../../../lib/event-time";
import { formatMoney } from "../../../lib/formatters/money";
import { eventFineAmountCents } from "../../../lib/adapters/events";

type ModalType = "create" | "checkin" | "excuse" | null;
type AttendanceStatus = "present" | "excused" | "absent";
type ManualTarget = { eventId: string; memberId: string; name: string };

interface EventDetailProps {
  detail: Event;
  attendance: RosterEntry[];
  attendanceLoading: boolean;
  attendanceError: string | null;
  eventsError: string | null;
  activeLink: CheckinLink | null;
  modal: ModalType;
  manualTarget: ManualTarget | null;
  manualStatus: AttendanceStatus;
  manualReason: string;
  isOfficer: boolean;
  onBack: () => void;
  onEventsRetry: () => void;
  onAttendanceRetry: () => void;
  onModalOpen: (m: ModalType) => void;
  onModalClose: () => void;
  onGenerateLink: () => void;
  onKillLink: () => void;
  onDeleteEvent: () => void;
  onSetManualTarget: (target: ManualTarget) => void;
  onClearManualTarget: () => void;
  onManualStatusChange: (s: AttendanceStatus) => void;
  onManualReasonChange: (r: string) => void;
  onManualConfirm: () => void;
  onProcessFines: () => void;
  onCheckinSuccess: (msg: string) => void;
  onExcuseSuccess: () => void;
}

export function EventDetail({
  detail, attendance, attendanceLoading, attendanceError, eventsError, activeLink,
  modal, manualTarget, manualStatus, manualReason, isOfficer,
  onBack, onEventsRetry, onAttendanceRetry, onModalOpen, onModalClose,
  onGenerateLink, onKillLink, onDeleteEvent, onSetManualTarget, onClearManualTarget,
  onManualStatusChange, onManualReasonChange, onManualConfirm, onProcessFines,
  onCheckinSuccess, onExcuseSuccess,
}: EventDetailProps) {
  const now = new Date();
  const isPast = isPastEvent(detail, now);

  return (
    <div>
      <button onClick={onBack} style={{ background: "none", border: "none", color: tokens.color.accentMuted, cursor: "pointer", fontSize: tokens.font.sizeMd, marginBottom: tokens.space[4], padding: 0 }}>
        ← Back to Events
      </button>
      {eventsError && (
        <ApiErrorBanner message={eventsError} onRetry={onEventsRetry} loading={false} />
      )}
      <Card style={{ marginBottom: tokens.space[4] }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: tokens.space[4] }}>
          <div>
            <h2 style={{ margin: 0, color: tokens.color.text, fontSize: 20 }}>{detail.title}</h2>
            <div style={{ color: tokens.color.textMuted, fontSize: tokens.font.sizeMd, marginTop: tokens.space[1] }}>
              {detail.date} at {detail.time} · {detail.location}
            </div>
          </div>
          <div style={{ display: "flex", gap: tokens.space[2] }}>
            {detail.required && <Badge color="purple">Required</Badge>}
            {/* fine_amount is legacy float dollars; eventFineAmountCents owns the float→cents boundary */}
          {detail.fine_amount > 0 && <Badge color="red">{formatMoney(eventFineAmountCents(detail))} fine</Badge>}
          </div>
        </div>
        {isOfficer && (
          <div style={{ display: "flex", gap: tokens.space[2], flexWrap: "wrap" }}>
            {!isPast && (
              !activeLink ? (
                <Btn onClick={onGenerateLink}><Icon type="link" size={14} /> Open Check-In</Btn>
              ) : (
                <Btn variant="danger" onClick={onKillLink}><Icon type="x" size={14} /> Close Check-In</Btn>
              )
            )}
            <Btn variant="danger" onClick={onDeleteEvent}>
              <Icon type="x" size={14} /> Delete Event
            </Btn>
          </div>
        )}
        {!isPast && !isOfficer && (
          <div style={{ display: "flex", gap: tokens.space[2] }}>
            <Btn onClick={() => onModalOpen("checkin")}><Icon type="check" size={14} /> Check In</Btn>
            <Btn variant="ghost" onClick={() => onModalOpen("excuse")}><Icon type="file" size={14} /> Submit Excuse</Btn>
          </div>
        )}
      </Card>

      {activeLink && <CheckinCodeCard link={activeLink} />}

      <AttendanceRoster
        attendance={attendance}
        loading={attendanceLoading}
        error={attendanceError}
        isOfficer={isOfficer}
        isPast={isPast}
        required={detail.required}
        fineAmount={detail.fine_amount}
        onRetry={onAttendanceRetry}
        onSetStatus={onSetManualTarget}
        onProcessFines={onProcessFines}
        eventId={detail.id}
      />

      {modal === "checkin" && (
        <Modal onClose={onModalClose}>
          <CheckInForm onSuccess={onCheckinSuccess} onClose={onModalClose} />
        </Modal>
      )}
      {modal === "excuse" && (
        <Modal onClose={onModalClose}>
          <ExcuseForm eventId={detail.id} eventTitle={detail.title} onSuccess={onExcuseSuccess} onClose={onModalClose} />
        </Modal>
      )}
      {manualTarget && (
        <ManualAttendanceModal
          target={manualTarget}
          status={manualStatus}
          reason={manualReason}
          onStatusChange={onManualStatusChange}
          onReasonChange={onManualReasonChange}
          onConfirm={onManualConfirm}
          onClose={onClearManualTarget}
        />
      )}
    </div>
  );
}

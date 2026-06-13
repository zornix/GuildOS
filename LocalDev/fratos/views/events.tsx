"use client";
import { useState, useEffect } from "react";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { Modal } from "../components/ui/modal";
import { Toast } from "../components/ui/toast";
import { Card } from "../components/ui/card";
import { ApiErrorBanner } from "../components/api-error-banner";
import { CreateEventForm } from "../components/forms/create-event-form";
import { EventTabs } from "../components/modules/events/event-tabs";
import { EventList } from "../components/modules/events/event-list";
import { EventCalendar } from "../components/modules/events/event-calendar";
import { EventDetail } from "../components/modules/events/event-detail";
import { Btn } from "../components/ui/btn";
import { Icon } from "../components/ui/icon";
import type { Event, RosterEntry, CheckinLink } from "../lib/types";
import { isPastEvent } from "../lib/event-time";
import { tokens } from "../config/theme/tokens";

type ModalType = "create" | "checkin" | "excuse" | null;
type AttendanceStatus = "present" | "excused" | "absent";
type ViewMode = "list" | "calendar";
type ManualTarget = { eventId: string; memberId: string; name: string };

export function EventsPage() {
  const { user } = useAuth();
  const [selected, setSelected] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalType>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [activeLink, setActiveLink] = useState<CheckinLink | null>(null);
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [manualTarget, setManualTarget] = useState<ManualTarget | null>(null);
  const [manualStatus, setManualStatus] = useState<AttendanceStatus>("present");
  const [manualReason, setManualReason] = useState("");

  const events = useApi<Event[]>(() => api.getEvents());
  const attendance = useApi<RosterEntry[]>(
    () => (selected ? api.getAttendance(selected) : Promise.resolve([])),
    [selected],
  );

  const reloadAttendance = attendance.reload;
  const reloadEvents = events.reload;

  useEffect(() => {
    if (!selected || user.role !== "officer") return;
    const t = setInterval(() => { reloadAttendance(); }, 12000);
    return () => clearInterval(t);
  }, [selected, user.role, reloadAttendance]);

  useEffect(() => {
    if (!selected) return;
    const onFocus = () => reloadAttendance();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [selected, reloadAttendance]);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api.getActiveCheckinLink(selected).then((res) => {
      if (cancelled) return;
      setActiveLink("short_code" in res && res.short_code ? (res as CheckinLink) : null);
    });
    return () => { cancelled = true; };
  }, [selected]);

  useEffect(() => {
    if (selected) return;
    const onFocus = () => reloadEvents();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [selected, reloadEvents]);

  const show = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 2500);
  };

  const now = new Date();
  const list = (events.data || []).filter((e) =>
    tab === "upcoming" ? !isPastEvent(e, now) : isPastEvent(e, now),
  );
  const detail = selected ? (events.data || []).find((e) => e.id === selected) : null;

  const generateLink = async () => {
    if (!selected) return;
    const link = await api.createCheckinLink(selected);
    setActiveLink(link);
  };

  const killLink = async () => {
    if (!selected) return;
    await api.killCheckinLink(selected);
    setActiveLink(null);
  };

  const deleteSelectedEvent = async () => {
    if (!selected || user.role !== "officer") return;
    if (!window.confirm("Delete this event? This cannot be undone.")) return;
    const eventId = selected;
    try {
      await api.deleteEvent(eventId);
      events.setData((prev) => (prev ? prev.filter((event) => event.id !== eventId) : prev));
      await events.reload();
      show("Event deleted");
      setSelected(null);
      setActiveLink(null);
    } catch (e: unknown) {
      show((e as Error).message || "Failed to delete event");
    }
  };

  const handleManualConfirm = async () => {
    if (!manualTarget) return;
    if (manualStatus === "excused" && !manualReason.trim()) {
      show("Excuse reason is required");
      return;
    }
    try {
      await api.manualCheckin(manualTarget.eventId, manualTarget.memberId, manualStatus, manualStatus === "excused" ? manualReason : undefined);
      show(`Marked ${manualTarget.name} as ${manualStatus}`);
      setManualTarget(null);
      attendance.reload();
    } catch (e: unknown) {
      show((e as Error).message || "Failed to update attendance");
    }
  };

  const handleProcessFines = async () => {
    if (!detail) return;
    const res = await api.processEventFines(detail.id);
    show(`${res.fines_issued} fine(s) issued for absent members without an approved excuse`);
    attendance.reload();
  };

  // Detail: selected event not found after load
  if (selected && !detail && !events.loading) {
    return (
      <div>
        <button type="button" onClick={() => setSelected(null)} style={{ background: "none", border: "none", color: tokens.color.accentMuted, cursor: "pointer", fontSize: tokens.font.sizeMd, marginBottom: tokens.space[4], padding: 0 }}>
          ← Back to Events
        </button>
        {events.error && (
          <ApiErrorBanner message={events.error} onRetry={events.reload} loading={events.loading} />
        )}
        <Card style={{ textAlign: "center", color: tokens.color.textMuted, padding: tokens.space[10] }}>
          {events.error ? "Events could not be loaded." : "This event is no longer available."}
        </Card>
        <Toast msg={toast} />
      </div>
    );
  }

  if (detail) {
    return (
      <>
        <EventDetail
          detail={detail}
          attendance={attendance.data || []}
          attendanceLoading={attendance.loading}
          attendanceError={attendance.error}
          eventsError={events.error}
          activeLink={activeLink}
          modal={modal}
          manualTarget={manualTarget}
          manualStatus={manualStatus}
          manualReason={manualReason}
          isOfficer={user.role === "officer"}
          onBack={() => { setSelected(null); setActiveLink(null); }}
          onEventsRetry={events.reload}
          onAttendanceRetry={attendance.reload}
          onModalOpen={setModal}
          onModalClose={() => setModal(null)}
          onGenerateLink={generateLink}
          onKillLink={killLink}
          onDeleteEvent={deleteSelectedEvent}
          onSetManualTarget={(target) => { setManualTarget(target); setManualStatus("present"); setManualReason(""); }}
          onClearManualTarget={() => setManualTarget(null)}
          onManualStatusChange={setManualStatus}
          onManualReasonChange={setManualReason}
          onManualConfirm={handleManualConfirm}
          onProcessFines={handleProcessFines}
          onCheckinSuccess={(msg) => { show(msg); setModal(null); }}
          onExcuseSuccess={() => { show("Excuse submitted"); setModal(null); }}
        />
        <Toast msg={toast} />
      </>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: tokens.space[3], marginBottom: tokens.space[4], flexWrap: "wrap" }}>
        <div style={{ display: "flex", gap: tokens.space[1], background: tokens.color.surface, borderRadius: tokens.radius.md, padding: 3, width: "fit-content" }}>
          {(["list", "calendar"] as const).map((mode) => (
            <Btn
              key={mode}
              variant={viewMode === mode ? "primary" : "ghost"}
              style={{ textTransform: "capitalize", padding: "6px 14px" }}
              onClick={() => setViewMode(mode)}
            >
              <Icon type={mode === "list" ? "check" : "cal"} size={14} /> {mode}
            </Btn>
          ))}
        </div>
        {user.role === "officer" && (
          <Btn onClick={() => setModal("create")}><Icon type="plus" size={14} /> New Event</Btn>
        )}
      </div>
      {events.error && (
        <ApiErrorBanner message={events.error} onRetry={events.reload} loading={events.loading} />
      )}
      {viewMode === "list" ? (
        <>
          <EventTabs tab={tab} onTabChange={setTab} />
          <EventList events={list} loading={events.loading} error={events.error} tab={tab} onSelectEvent={setSelected} />
        </>
      ) : (
        <EventCalendar
          events={events.data || []}
          loading={events.loading}
          error={events.error}
          onSelectEvent={setSelected}
        />
      )}
      {modal === "create" && (
        <Modal onClose={() => setModal(null)}>
          <CreateEventForm onSuccess={() => { reloadEvents(); setModal(null); }} onClose={() => setModal(null)} />
        </Modal>
      )}
      <Toast msg={toast} />
    </div>
  );
}

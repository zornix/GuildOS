"use client";
import { useState, useEffect } from "react";
import { useAuth } from "../hooks/use-auth";
import { useApi } from "../hooks/use-api";
import { api } from "../lib/api-client";
import { T } from "../lib/theme";
import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Btn } from "../components/ui/btn";
import { Icon } from "../components/ui/icon";
import { Avatar } from "../components/ui/avatar";
import { Modal } from "../components/ui/modal";
import { Toast } from "../components/ui/toast";
import { Countdown } from "../components/countdown";
import { CreateEventForm } from "../components/forms/create-event-form";
import { CheckInForm } from "../components/forms/check-in-form";
import { ExcuseForm } from "../components/forms/excuse-form";
import type { Event, RosterEntry, CheckinLink } from "../lib/types";
import { isPastEvent } from "../lib/event-time";
import { ApiErrorBanner } from "../components/api-error-banner";

export function EventsPage() {
  const { user } = useAuth();
  const [selected, setSelected] = useState<string | null>(null);
  const [modal, setModal] = useState<"create" | "checkin" | "excuse" | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [activeLink, setActiveLink] = useState<CheckinLink | null>(null);
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");
  const [manualTarget, setManualTarget] = useState<{ eventId: string; memberId: string; name: string } | null>(null);
  const [manualStatus, setManualStatus] = useState<"present" | "excused" | "absent">("present");
  const [manualReason, setManualReason] = useState("");
  const events = useApi<Event[]>(() => api.getEvents());
  const attendance = useApi<RosterEntry[]>(
    () => (selected ? api.getAttendance(selected) : Promise.resolve([])),
    [selected],
  );

  useEffect(() => {
    if (!selected || user.role !== "officer") return;
    const t = setInterval(() => {
      attendance.reload();
    }, 12000);
    return () => clearInterval(t);
  }, [selected, user.role, attendance]);

  useEffect(() => {
    if (!selected) return;
    const onFocus = () => attendance.reload();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [selected, attendance]);

  // Restore active check-in link from server when entering event detail
  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    api.getActiveCheckinLink(selected).then((res) => {
      if (cancelled) return;
      setActiveLink("short_code" in res && res.short_code ? (res as CheckinLink) : null);
    });
    return () => { cancelled = true; };
  }, [selected]);

  // Refresh event list when window regains focus (picks up new DB rows)
  useEffect(() => {
    if (selected) return;
    const onFocus = () => events.reload();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [selected, events]);

  const show = (m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 2500);
  };

  const now = new Date();
  const list = (events.data || []).filter((e) =>
    tab === "upcoming" ? !isPastEvent(e, now) : isPastEvent(e, now),
  );
  const detail = selected ? (events.data || []).find((e) => e.id === selected) : null;

  if (selected && !detail && !events.loading) {
    return (
      <div>
        <button
          type="button"
          onClick={() => setSelected(null)}
          style={{ background: "none", border: "none", color: T.acl, cursor: "pointer", fontSize: 13, marginBottom: 16, padding: 0 }}
        >
          ← Back to Events
        </button>
        {events.error && (
          <ApiErrorBanner message={events.error} onRetry={events.reload} loading={events.loading} />
        )}
        <Card style={{ textAlign: "center", color: T.txm, padding: 40 }}>
          {events.error ? "Events could not be loaded." : "This event is no longer available."}
        </Card>
      </div>
    );
  }

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
    try {
      await api.deleteEvent(selected);
      show("Event deleted");
      setSelected(null);
      setActiveLink(null);
      events.reload();
    } catch (e: unknown) {
      show((e as Error).message || "Failed to delete event");
    }
  };

  if (detail) {
    const isPast = isPastEvent(detail, now);
    return (
      <div>
        <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", color: T.acl, cursor: "pointer", fontSize: 13, marginBottom: 16, padding: 0 }}>
          ← Back to Events
        </button>
        {events.error && (
          <ApiErrorBanner message={events.error} onRetry={events.reload} loading={events.loading} />
        )}
        <Card style={{ marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
            <div>
              <h2 style={{ margin: 0, color: T.tx, fontSize: 20 }}>{detail.title}</h2>
              <div style={{ color: T.txm, fontSize: 13, marginTop: 4 }}>{detail.date} at {detail.time} · {detail.location}</div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              {detail.required && <Badge color="purple">Required</Badge>}
              {detail.fine_amount > 0 && <Badge color="red">${detail.fine_amount} fine</Badge>}
            </div>
          </div>
          {user.role === "officer" && (
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {!isPast && (
                !activeLink ? (
                  <Btn onClick={generateLink}><Icon type="link" size={14} /> Open Check-In</Btn>
                ) : (
                  <Btn variant="danger" onClick={killLink}><Icon type="x" size={14} /> Close Check-In</Btn>
                )
              )}
              <Btn variant="danger" onClick={deleteSelectedEvent}>
                <Icon type="x" size={14} /> Delete Event
              </Btn>
            </div>
          )}
          {!isPast && user.role !== "officer" && (
            <div style={{ display: "flex", gap: 10 }}>
              <Btn onClick={() => setModal("checkin")}><Icon type="check" size={14} /> Check In</Btn>
              <Btn variant="ghost" onClick={() => setModal("excuse")}><Icon type="file" size={14} /> Submit Excuse</Btn>
            </div>
          )}
        </Card>

        {activeLink && (
          <Card style={{ marginBottom: 16, textAlign: "center", background: `linear-gradient(135deg, ${T.ac}15, ${T.sf})` }}>
            <div style={{ fontSize: 11, color: T.txm, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Check-In Link Active</div>
            <div style={{ fontFamily: "monospace", fontSize: 28, fontWeight: 800, color: T.tx, letterSpacing: 4, margin: "8px 0", background: T.bg, display: "inline-block", padding: "10px 24px", borderRadius: 12 }}>
              /c/{activeLink.short_code}
            </div>
            <div style={{ marginTop: 8, fontSize: 13, color: T.txm }}>
              Full link: <span style={{ color: T.acl, fontFamily: "monospace" }}>{activeLink.url || `fraternityos.vercel.app/c/${activeLink.short_code}`}</span>
            </div>
            <div style={{ marginTop: 12 }}>
              <span style={{ fontSize: 12, color: T.txm, marginRight: 8 }}>Expires in:</span>
              <Countdown expiresAt={activeLink.expires_at} />
            </div>
          </Card>
        )}

        <Card>
          {attendance.error && (
            <ApiErrorBanner message={attendance.error} onRetry={attendance.reload} loading={attendance.loading} />
          )}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 12 }}>
            <h3 style={{ margin: 0, color: T.tx, fontSize: 15 }}>
              Attendance ({(attendance.data || []).filter((a) => a.checked_in).length}/{(attendance.data || []).length})
            </h3>
            {user.role === "officer" && isPast && detail.required && detail.fine_amount > 0 && (
              <Btn
                variant="danger"
                style={{ padding: "6px 12px", fontSize: 12 }}
                onClick={async () => {
                  const res = await api.processEventFines(detail.id);
                  show(`${res.fines_issued} fine(s) issued for absent members without an approved excuse`);
                  attendance.reload();
                }}
              >
                <Icon type="dollar" size={14} /> Fine unexcused absences
              </Btn>
            )}
          </div>
          {attendance.loading && !(attendance.data || []).length ? (
            <div style={{ color: T.txm, textAlign: "center", padding: 24 }}>Loading attendance…</div>
          ) : attendance.error && !(attendance.data || []).length ? (
            <div style={{ color: T.txm, fontSize: 13, padding: 16, textAlign: "center" }}>Could not load attendance. Use Retry above.</div>
          ) : (
          <div style={{ display: "grid", gap: 6 }}>
            {(attendance.data || []).map((m) => (
              <div key={m.member_id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", borderRadius: 8, background: T.bg }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <Avatar name={m.name} />
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: T.tx }}>{m.name}</div>
                    {m.checked_in_at && <div style={{ fontSize: 10, color: T.txm }}>{new Date(m.checked_in_at).toLocaleTimeString()} · {m.method}</div>}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                  {m.checked_in ? (
                    <Badge color="green">Present</Badge>
                  ) : m.excuse_status === "approved" ? (
                    <Badge color="blue">Excused</Badge>
                  ) : m.excuse_status ? (
                    <Badge color={m.excuse_status === "denied" ? "red" : "yellow"}>{m.excuse_status}</Badge>
                  ) : (
                    <Badge color="red">Absent</Badge>
                  )}
                  {user.role === "officer" && (
                    <Btn variant="ghost" style={{ padding: "2px 8px", fontSize: 10 }} onClick={() => {
                      setManualTarget({ eventId: detail.id, memberId: m.member_id, name: m.name });
                      setManualStatus("present");
                      setManualReason("");
                    }}>
                      Set Status
                    </Btn>
                  )}
                </div>
              </div>
            ))}
          </div>
          )}
        </Card>

        {modal === "checkin" && (
          <Modal onClose={() => setModal(null)}>
            <CheckInForm onSuccess={(msg) => { show(msg); setModal(null); }} onClose={() => setModal(null)} />
          </Modal>
        )}
        {modal === "excuse" && (
          <Modal onClose={() => setModal(null)}>
            <ExcuseForm eventId={detail.id} eventTitle={detail.title} onSuccess={() => { show("Excuse submitted"); setModal(null); }} onClose={() => setModal(null)} />
          </Modal>
        )}
        {manualTarget && (
          <Modal onClose={() => setManualTarget(null)}>
            <Card style={{ maxWidth: 400, margin: "0 auto" }}>
              <h3 style={{ margin: "0 0 12px", color: T.tx, fontSize: 16 }}>Set Attendance — {manualTarget.name}</h3>
              <div style={{ display: "flex", gap: 6, marginBottom: 14 }}>
                {(["present", "excused", "absent"] as const).map((s) => (
                  <Btn key={s} variant={manualStatus === s ? "primary" : "ghost"} style={{ textTransform: "capitalize", padding: "6px 14px", flex: 1 }} onClick={() => setManualStatus(s)}>
                    {s}
                  </Btn>
                ))}
              </div>
              {manualStatus === "excused" && (
                <div style={{ marginBottom: 14 }}>
                  <label style={{ fontSize: 12, color: T.txm, display: "block", marginBottom: 4 }}>Excuse reason (required)</label>
                  <textarea
                    value={manualReason}
                    onChange={(e) => setManualReason(e.target.value)}
                    placeholder="Enter excuse reason..."
                    style={{ width: "100%", minHeight: 70, padding: 8, borderRadius: 8, border: `1px solid ${T.bd}`, background: T.bg, color: T.tx, fontSize: 13, resize: "vertical", fontFamily: "inherit" }}
                  />
                </div>
              )}
              <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                <Btn variant="ghost" onClick={() => setManualTarget(null)}>Cancel</Btn>
                <Btn
                  onClick={async () => {
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
                  }}
                >
                  Confirm
                </Btn>
              </div>
            </Card>
          </Modal>
        )}
        <Toast msg={toast} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 4, background: T.sf, borderRadius: 8, padding: 3 }}>
          {(["upcoming", "past"] as const).map((t) => (
            <Btn key={t} variant={tab === t ? "primary" : "ghost"} style={{ textTransform: "capitalize", padding: "6px 14px" }} onClick={() => setTab(t)}>
              {t}
            </Btn>
          ))}
        </div>
        {user.role === "officer" && <Btn onClick={() => setModal("create")}><Icon type="plus" size={14} /> New Event</Btn>}
      </div>
      {events.error && (
        <ApiErrorBanner message={events.error} onRetry={events.reload} loading={events.loading} />
      )}
      {events.loading && !(events.data || []).length ? (
        <div style={{ color: T.txm, textAlign: "center", padding: 40 }}>Loading events…</div>
      ) : list.length === 0 ? (
        <Card style={{ textAlign: "center", color: T.txm, padding: 40 }}>
          {events.error ? `Could not load events (${tab}). Use Retry above.` : `No ${tab} events`}
        </Card>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {list.map((e) => (
            <Card key={e.id} onClick={() => setSelected(e.id)} style={{ padding: 16, display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: T.tx }}>{e.title}</div>
                <div style={{ fontSize: 12, color: T.txm, marginTop: 2 }}>{e.date} at {e.time} · {e.location}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {e.required && <Badge color="purple">Required</Badge>}
                {e.fine_amount > 0 && <Badge color="red">${e.fine_amount}</Badge>}
                <span style={{ color: T.txm }}><Icon type="chev" size={14} /></span>
              </div>
            </Card>
          ))}
        </div>
      )}
      {modal === "create" && (
        <Modal onClose={() => setModal(null)}>
          <CreateEventForm onSuccess={() => { events.reload(); setModal(null); }} onClose={() => setModal(null)} />
        </Modal>
      )}
    </div>
  );
}

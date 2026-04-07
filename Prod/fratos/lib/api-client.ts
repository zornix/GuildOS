import type {
  Member,
  Event,
  Excuse,
  Fine,
  CheckinLink,
  FineSummary,
  InviteResult,
  RosterEntry,
  MemberStanding,
} from "./types";

function formatApiErrorDetail(data: unknown): string {
  const d = (data as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    const parts = d
      .map((item) => (item && typeof item === "object" && "msg" in item ? String((item as { msg: string }).msg) : null))
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return "Request failed";
}

/** When unset, same-origin `/api` works on Vercel. In local dev, Next.js is on :3000 and the API is on :8001. */
function apiBase(): string {
  const explicit = process.env.NEXT_PUBLIC_API_BASE;
  if (explicit) return explicit;
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "localhost" || h === "127.0.0.1") return "http://127.0.0.1:8001";
  }
  return "";
}

class ApiClient {
  private token: string | null = null;

  setToken(t: string | null) {
    this.token = t;
    if (t) {
      localStorage.setItem("auth_token", t);
    } else {
      localStorage.removeItem("auth_token");
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("auth_token");
      if (saved) {
        this.token = saved;
        return saved;
      }
    }
    return null;
  }

  async request<T = unknown>(path: string, opts: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = this.getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${apiBase()}${path}`, { ...opts, headers });
    const text = await res.text();
    let data: unknown = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      throw new Error(
        `API returned non-JSON (${res.status}). For local dev, run the FastAPI server on port 8001 or set NEXT_PUBLIC_API_BASE.`,
      );
    }
    if (!res.ok) throw new Error(formatApiErrorDetail(data));
    return data as T;
  }

  // Auth
  login(email: string) {
    return this.request<{ access_token?: string; message?: string; ok?: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }
  getMe() {
    return this.request<Member>("/api/auth/me");
  }
  invite(emails: string[]) {
    return this.request<InviteResult>("/api/auth/invite", {
      method: "POST",
      body: JSON.stringify({ emails }),
    });
  }

  // Events
  getEvents() {
    return this.request<Event[]>("/api/events");
  }
  getEvent(id: string) {
    return this.request<Event>(`/api/events/${id}`);
  }
  createEvent(data: Partial<Event>) {
    return this.request<Event>("/api/events", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }
  deleteEvent(id: string) {
    return this.request<{ deleted: boolean }>(`/api/events/${id}`, { method: "DELETE" });
  }

  // Check-in links
  createCheckinLink(eventId: string) {
    return this.request<CheckinLink>(`/api/events/${eventId}/checkin-link`, { method: "POST" });
  }
  killCheckinLink(eventId: string) {
    return this.request<{ deactivated: boolean }>(`/api/events/${eventId}/checkin-link`, { method: "DELETE" });
  }

  // Attendance
  checkinViaLink(code: string) {
    return this.request<{ status: string; event_title: string }>(`/api/attendance/checkin/${code}`, { method: "POST" });
  }
  getAttendance(eventId: string) {
    return this.request<RosterEntry[]>(`/api/attendance/event/${eventId}`);
  }
  manualCheckin(eventId: string, memberId: string) {
    return this.request<{ status: string; method: string }>(
      `/api/attendance/event/${eventId}/manual/${memberId}`,
      { method: "POST" },
    );
  }

  // Excuses
  submitExcuse(eventId: string, reason: string) {
    return this.request<Excuse>(`/api/excuses/event/${eventId}`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
  }
  getExcuses(status?: string | null) {
    return this.request<Excuse[]>(`/api/excuses${status ? `?status=${status}` : ""}`);
  }
  reviewExcuse(id: string, status: string) {
    return this.request<Excuse>(`/api/excuses/${id}/review`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    });
  }

  // Fines
  getFines(status?: string | null) {
    return this.request<Fine[]>(`/api/fines${status ? `?status=${status}` : ""}`);
  }
  waiveFine(id: string) {
    return this.request<Fine>(`/api/fines/${id}/waive`, { method: "POST" });
  }
  getFineSummary() {
    return this.request<FineSummary>("/api/fines/summary");
  }
  processEventFines(eventId: string) {
    return this.request<{ event_id: string; fines_issued: number }>(
      `/api/fines/process-event/${eventId}`,
      { method: "POST" },
    );
  }

  // Members
  getMembers() {
    return this.request<Member[]>("/api/members");
  }
  updateRole(memberId: string, role: string) {
    return this.request<Member>(`/api/members/${memberId}/role?role=${role}`, {
      method: "PUT",
    });
  }

  // Standing
  getStandings() {
    return this.request<MemberStanding[]>("/api/standing");
  }
}

export const api = new ApiClient();

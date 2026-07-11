import type {
  Member,
  Event,
  Excuse,
  CheckinLink,
  ActiveCheckinLinkRow,
  FineSummary,
  InviteResult,
  RosterEntry,
  MemberStanding,
  MyPermissions,
  RoleCatalogEntry,
  MemberRole,
  Task,
  TaskStatus,
  Announcement,
  AnnouncementAudience,
  Recruit,
  RecruitStage,
  BylawsDocument,
  BylawsQueryResult,
  CommandRequest,
} from "./types";
import type {
  TreasuryDashboardApiResponse,
  TreasuryPaymentSubmissionsPage,
  TreasuryReportDataset,
  TreasurySubmissionStatus,
} from "./contracts/treasury";
import type { FineApiRow } from "./contracts/fines";

/** Thrown for failed HTTP responses so callers can inspect `status` (e.g. retries). */
export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

const READ_RETRY_MAX_ATTEMPTS = 3;
const READ_RETRY_BASE_MS = 150;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetriableReadFailure(err: unknown): boolean {
  if (err instanceof ApiRequestError) {
    const s = err.status;
    if (s === undefined) return false;
    return s === 408 || s === 429 || s >= 500;
  }
  if (err instanceof Error && err.message.includes("Network request failed")) return true;
  return false;
}

function formatApiErrorDetail(data: unknown): string {
  const d = (data as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  if (d && typeof d === "object" && !Array.isArray(d)) {
    const obj = d as { message?: string; code?: string };
    if (obj.message) return obj.code ? `${obj.code}: ${obj.message}` : obj.message;
  }
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
  // If explicitly configured, always honor it. This keeps prod behavior stable
  // and avoids auth header loss across proxy/rewrite layers.
  if (explicit) return explicit;
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "localhost" || h === "127.0.0.1") return "http://127.0.0.1:8001";
  }
  return "";
}

export class ApiClient {
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

  private headers(): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    const token = this.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
  }

  async request<T = unknown>(path: string, opts: RequestInit = {}): Promise<T> {
    const url = `${apiBase()}${path}`;
    let res: Response;
    try {
      res = await fetch(url, { ...opts, headers: this.headers() });
    } catch {
      throw new Error(
        `Network request failed for ${path}. Check API URL/CORS configuration and verify backend reachability.`,
      );
    }
    const text = await res.text();
    let data: unknown = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      throw new ApiRequestError(
        `API returned non-JSON (${res.status}). For local dev, run the FastAPI server on port 8001 or set NEXT_PUBLIC_API_BASE.`,
        res.status,
      );
    }
    if (!res.ok) throw new ApiRequestError(formatApiErrorDetail(data), res.status);
    return data as T;
  }

  async requestText(path: string, opts: RequestInit = {}): Promise<string> {
    const url = `${apiBase()}${path}`;
    let res: Response;
    try {
      res = await fetch(url, { ...opts, headers: this.headers() });
    } catch {
      throw new Error(
        `Network request failed for ${path}. Check API URL/CORS configuration and verify backend reachability.`,
      );
    }
    const text = await res.text();
    if (!res.ok) {
      try {
        throw new ApiRequestError(formatApiErrorDetail(JSON.parse(text)), res.status);
      } catch (e) {
        if (e instanceof ApiRequestError) throw e;
        throw new ApiRequestError(text || "Request failed", res.status);
      }
    }
    return text;
  }

  /** Idempotent GET with bounded exponential backoff on transient failures. */
  private async requestRead<T>(path: string): Promise<T> {
    let lastErr: unknown;
    for (let attempt = 0; attempt < READ_RETRY_MAX_ATTEMPTS; attempt++) {
      try {
        return await this.request<T>(path, { method: "GET" });
      } catch (e) {
        lastErr = e;
        if (!isRetriableReadFailure(e) || attempt === READ_RETRY_MAX_ATTEMPTS - 1) {
          throw e;
        }
        await sleep(READ_RETRY_BASE_MS * 2 ** attempt);
      }
    }
    throw lastErr;
  }

  // Auth
  login(email: string, password?: string) {
    const body: { email: string; password?: string } = { email };
    if (password) body.password = password;
    return this.request<{ access_token?: string; message?: string; ok?: boolean; password_setup_required?: boolean }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }
  devLogin(email: string) {
    return this.request<{ access_token?: string; token_type?: string }>("/api/auth/dev-login", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  }
  setPassword(password: string) {
    return this.request<{ message: string }>("/api/auth/set-password", {
      method: "POST",
      body: JSON.stringify({ password }),
    });
  }
  getMe() {
    return this.requestRead<Member>("/api/auth/me");
  }
  invite(emails: string[]) {
    return this.request<InviteResult>("/api/auth/invite", {
      method: "POST",
      body: JSON.stringify({ emails }),
    });
  }

  // Events
  getEvents() {
    return this.requestRead<Event[]>("/api/events");
  }
  getEvent(id: string) {
    return this.requestRead<Event>(`/api/events/${id}`);
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
  getActiveCheckinLink(eventId: string) {
    return this.requestRead<CheckinLink | Record<string, never>>(`/api/events/${eventId}/checkin-link`);
  }
  createCheckinLink(eventId: string) {
    return this.request<CheckinLink>(`/api/events/${eventId}/checkin-link`, { method: "POST" });
  }
  killCheckinLink(eventId: string) {
    return this.request<{ deactivated: boolean }>(`/api/events/${eventId}/checkin-link`, { method: "DELETE" });
  }
  listActiveCheckinLinks() {
    return this.requestRead<ActiveCheckinLinkRow[]>("/api/checkin-links/active");
  }

  // Attendance
  checkinViaLink(code: string) {
    return this.request<{ status: string; event_title: string }>(`/api/attendance/checkin/${code}`, { method: "POST" });
  }
  getAttendance(eventId: string) {
    return this.requestRead<RosterEntry[]>(`/api/attendance/event/${eventId}`);
  }
  manualCheckin(eventId: string, memberId: string, status: "present" | "excused" | "absent" = "present", reason?: string) {
    return this.request<{ status: string; method: string }>(
      `/api/attendance/event/${eventId}/manual/${memberId}`,
      { method: "POST", body: JSON.stringify({ status, reason }) },
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
    return this.requestRead<Excuse[]>(`/api/excuses${status ? `?status=${status}` : ""}`);
  }
  reviewExcuse(id: string, status: string) {
    return this.request<Excuse>(`/api/excuses/${id}/review`, {
      method: "PUT",
      body: JSON.stringify({ status }),
    });
  }

  // Fines
  getFines(status?: string | null) {
    return this.requestRead<FineApiRow[]>(`/api/fines${status ? `?status=${status}` : ""}`);
  }
  waiveFine(id: string) {
    return this.request<Record<string, unknown>>(`/api/fines/${id}/waive`, { method: "POST" });
  }
  getFineSummary() {
    return this.requestRead<FineSummary>("/api/fines/summary");
  }
  processEventFines(eventId: string) {
    return this.request<{ event_id: string; fines_issued: number }>(
      `/api/fines/process-event/${eventId}`,
      { method: "POST" },
    );
  }

  // Members
  getMembers() {
    return this.requestRead<Member[]>("/api/members");
  }
  updateRole(memberId: string, role: string) {
    return this.request<Member>(`/api/members/${memberId}/role?role=${role}`, {
      method: "PUT",
    });
  }

  // Standing
  getStandings() {
    return this.requestRead<MemberStanding[]>("/api/standing");
  }

  // Treasury
  getTreasuryDashboard() {
    return this.requestRead<TreasuryDashboardApiResponse>("/api/treasury/dashboard");
  }
  getTreasuryPaymentSubmissions(
    status: TreasurySubmissionStatus = "pending",
    limit = 10,
    cursor?: string | null,
  ) {
    const params = new URLSearchParams({ status, limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return this.requestRead<TreasuryPaymentSubmissionsPage>(`/api/treasury/payments/submissions?${params.toString()}`);
  }
  getTreasuryReport(period: string, dataset: TreasuryReportDataset) {
    const params = new URLSearchParams({ period, dataset });
    return this.requestText(`/api/treasury/report?${params.toString()}`, { method: "GET" });
  }

  // RBAC
  getMyPermissions() {
    return this.requestRead<MyPermissions>("/api/rbac/me/permissions");
  }
  getRoleCatalog() {
    return this.requestRead<RoleCatalogEntry[]>("/api/rbac/roles");
  }
  getMemberRoles(memberId: string) {
    return this.requestRead<MemberRole[]>(`/api/rbac/members/${memberId}/roles`);
  }
  assignRole(memberId: string, roleKey: string) {
    return this.request<MemberRole>(`/api/rbac/members/${memberId}/roles`, {
      method: "POST",
      body: JSON.stringify({ role_key: roleKey }),
    });
  }
  revokeRole(memberId: string, roleKey: string) {
    return this.request<{ revoked: boolean }>(`/api/rbac/members/${memberId}/roles/${roleKey}`, {
      method: "DELETE",
    });
  }

  // Tasks
  getTasks() {
    return this.requestRead<Task[]>("/api/tasks/");
  }
  createTask(data: { title: string; description?: string; assigned_member_id?: string; required?: boolean; due_at?: string }) {
    return this.request<Task>("/api/tasks/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }
  updateTaskStatus(taskId: string, status: TaskStatus) {
    return this.request<Task>(`/api/tasks/${taskId}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    });
  }

  // Announcements
  getAnnouncements() {
    return this.requestRead<Announcement[]>("/api/announcements/");
  }
  createAnnouncement(data: { title: string; body: string; audience?: AnnouncementAudience }) {
    return this.request<Announcement>("/api/announcements/", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }
  sendAnnouncement(id: string) {
    return this.request<Announcement>(`/api/announcements/${id}/send`, { method: "POST" });
  }

  // Recruitment
  getRecruits() {
    return this.requestRead<Recruit[]>("/api/recruitment/recruits");
  }
  createRecruit(data: { name: string; email?: string; phone?: string; notes?: string }) {
    return this.request<Recruit>("/api/recruitment/recruits", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }
  updateRecruitStage(id: string, stage: RecruitStage) {
    return this.request<Recruit>(`/api/recruitment/recruits/${id}/stage`, {
      method: "POST",
      body: JSON.stringify({ stage }),
    });
  }

  // Bylaws
  getBylawsDocuments() {
    return this.requestRead<BylawsDocument[]>("/api/bylaws/documents");
  }
  createBylawsDocument(data: { title: string; content: string }) {
    return this.request<BylawsDocument>("/api/bylaws/documents", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }
  queryBylaws(question: string) {
    return this.request<BylawsQueryResult>("/api/bylaws/query", {
      method: "POST",
      body: JSON.stringify({ question }),
    });
  }

  // NL controller
  getCommands() {
    return this.requestRead<CommandRequest[]>("/api/nl-controller/commands");
  }
  submitCommand(inputText: string) {
    return this.request<CommandRequest>("/api/nl-controller/commands", {
      method: "POST",
      body: JSON.stringify({ input_text: inputText }),
    });
  }
  reviewCommand(id: string, decision: "approve" | "reject") {
    return this.request<CommandRequest>(`/api/nl-controller/commands/${id}/review`, {
      method: "POST",
      body: JSON.stringify({ decision }),
    });
  }
}

export const api = new ApiClient();

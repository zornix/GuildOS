// Thin fetch client for the real GuildOS FastAPI backend.
// Vite proxies /api -> http://localhost:8001 (see vite.config.ts).
// Auth is dev-login only: this prototype always acts as the seeded officer.

const TOKEN_KEY = 'g_token';
const DEV_EMAIL = 'jake@tke.org';

async function devLogin(): Promise<string> {
  const res = await fetch('/api/auth/dev-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: DEV_EMAIL })
  });
  if (!res.ok) throw new Error(`dev-login failed (${res.status})`);
  const data = await res.json();
  localStorage.setItem(TOKEN_KEY, data.access_token);
  return data.access_token as string;
}

export async function ensureLogin(): Promise<string> {
  return localStorage.getItem(TOKEN_KEY) || devLogin();
}

async function request<T>(method: string, path: string, body?: unknown, retry = true): Promise<T> {
  const token = await ensureLogin();
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: body === undefined ? undefined : JSON.stringify(body)
  });

  if (res.status === 401 && retry) {
    localStorage.removeItem(TOKEN_KEY);
    await devLogin();
    return request<T>(method, path, body, false);
  }

  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed.detail === 'string' ? parsed.detail : text;
    } catch { /* non-JSON error body */ }
    throw Object.assign(
      new Error(`${method} ${path} failed (${res.status}): ${detail.substring(0, 160)}`),
      { status: res.status }
    );
  }
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Officer-gated reads answer 403 for a member session, which means "this
 *  section is empty for you", not "the backend is down". Only 403 is swallowed;
 *  anything else propagates so a real outage still reads as one. */
export async function optionalOfficerCall<T, F>(call: Promise<T>, fallback: F): Promise<T | F> {
  try {
    return await call;
  } catch (err) {
    if ((err as { status?: number }).status === 403) return fallback;
    throw err;
  }
}

// ----------------------------------------------------
// BACKEND DTOs (snake_case, exactly as the API returns them)
// ----------------------------------------------------
export interface MeDto { id: string; name: string; email: string; role: string; chapter_id: string; }

export interface MemberDto { id: string; name: string; email: string; role: string; status: string; }

export interface StandingDto {
  member_id: string;
  name: string;
  email: string;
  standing: string;
  attended: number;
  total_required: number;
  unexcused_absences: number;
  unpaid_fines: number;
  unpaid_amount_cents: number;
}

export interface EventDto {
  id: string;
  title: string;
  description?: string | null;
  date: string;
  time: string;
  end_time?: string | null;
  location: string;
  required: boolean;
  event_type?: string | null;
  visibility?: string | null;
  attendance_count?: number;
  organizer_count?: number;
  job_count?: number;
  open_job_count?: number;
}

/** GET /api/events/{id} — the list row plus the rows only the detail endpoint
 *  carries: supervisors (the creator is auto-added), organizers, the live
 *  attendance count and the last notify blast. */
export interface EventDetailDto extends EventDto {
  supervisors: { member_id: string; is_creator: boolean; name?: string | null }[];
  organizers: { id: string; member_id: string; source: string; created_at: string }[];
  last_notified_at?: string | null;
}

/** Check-in link. GET answers `{}` when no link is live. */
export interface CheckInLinkDto {
  short_code?: string;
  url?: string;
  expires_at?: string;
}

export interface NotifyPreviewDto {
  recipient_count: number;
  no_phone_count: number;
  body_preview: string;
  last_notified_at: string | null;
}

export interface ScoreDto {
  member_id: string;
  name: string;
  email: string;
  score: number;
  prior_security_shifts: number;
}

export interface SwapDto {
  id: string;
  task_id: string;
  event_id: string;
  requester_member_id: string;
  target_member_id: string;
  note: string | null;
  status: string;
  created_at: string | null;
}

export interface SecurityAssignmentDto {
  task_id: string;
  event_id: string;
  member_id: string | null;
  status: string;
  rejection_reason: string | null;
  pending_swap: SwapDto | null;
}

export interface ExcuseDto {
  id: string;
  event_id: string;
  member_id: string;
  reason: string;
  status: string;
  submitted_at: string;
  reviewed_by?: string | null;
  members?: { name: string; email: string } | null;
  events?: { title: string; date: string } | null;
}

export interface FineDto {
  id: string;
  amount_cents: number;
  status: string;
  reason: string;
  issued_at: string | null;
  member_id: string | null;
  member_name: string | null;
  event_id: string | null;
  event_title: string | null;
  event_date: string | null;
}

export interface VerifiedPaymentDto {
  id: string;
  member_id: string;
  invoice_id: string;
  amount_cents: number;
  verified_at?: string | null;
  created_at?: string | null;
}

export interface TreasuryDashboardDto {
  chapter_balance_cents: number;
  total_outstanding_cents: number;
  pending_proof_count: number;
  overdue_invoice_count: number;
  members_with_balance_count: number;
  recent_payments: VerifiedPaymentDto[];
}

export interface TaskDto {
  id: string;
  title: string;
  description: string | null;
  assigned_member_id: string | null;
  status: string;
  required: boolean;
  due_at: string | null;
  created_at: string;
  // Job fields (V1): a task is a job on an event OR an initiative, never both.
  event_id: string | null;
  initiative_id: string | null;
  kind: string; // 'standard' | 'security'
  people_needed: number;
  claimants: string[]; // member ids with an active commitment
  claimed_count: number;
  rejection_reason?: string | null;
}

export interface AnnouncementDto {
  id: string;
  title: string;
  body: string;
  audience: string;
  status: string;
  created_by: string | null;
  sent_at: string | null;
  created_at: string;
  // D15 calendar slot: a dated announcement also shows on the calendar.
  calendar_date?: string | null;
  calendar_time?: string | null;
  hidden_from_calendar?: boolean;
}

export interface RecruitDto {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  stage: string;
  notes: string | null;
  created_at: string;
}

export interface InitiativeDto {
  id: string;
  title: string;
  description: string | null;
  date: string;
  time: string;
  end_date: string | null;
  chair_member_ids: string[];
}

// ----------------------------------------------------
// ENDPOINTS (paths are the exact mounted ones — trailing slashes matter)
// ----------------------------------------------------
export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),

  getMe: () => request<MeDto>('GET', '/api/auth/me'),

  getMembers: () => request<MemberDto[]>('GET', '/api/members/'),
  getStandings: () => request<StandingDto[]>('GET', '/api/standing/'),
  // Officer-gated (STANDING_VIEW_ALL): callers must tolerate a 403.
  getScores: () => request<ScoreDto[]>('GET', '/api/memberadmin/scores'),

  getEvents: () => request<EventDto[]>('GET', '/api/events/'),
  getEvent: (id: string) => request<EventDetailDto>('GET', `/api/events/${id}`),
  createEvent: (body: Record<string, unknown>) => request<EventDto>('POST', '/api/events/', body),
  updateEvent: (id: string, body: Record<string, unknown>) =>
    request<EventDto>('PUT', `/api/events/${id}`, body),

  /** Self-volunteer: an omitted member_id means the signed-in member. */
  addOrganizer: (eventId: string) =>
    request<unknown>('POST', `/api/events/${eventId}/organizers`, {}),

  notifyPreview: (eventId: string) =>
    request<NotifyPreviewDto>('GET', `/api/events/${eventId}/notify-preview`),
  /** Two-phase confirm: the count must still match what the preview resolved. */
  notifyEvent: (eventId: string, confirmedRecipientCount: number) =>
    request<unknown>('POST', `/api/events/${eventId}/notify`, {
      confirmed_recipient_count: confirmedRecipientCount
    }),

  getCheckInLink: (eventId: string) =>
    request<CheckInLinkDto>('GET', `/api/events/${eventId}/checkin-link`),
  openCheckInLink: (eventId: string) =>
    request<CheckInLinkDto>('POST', `/api/events/${eventId}/checkin-link`),
  closeCheckInLink: (eventId: string) =>
    request<void>('DELETE', `/api/events/${eventId}/checkin-link`),
  /** Door-code check-in; the backend checks in the signed-in member. */
  checkInWithCode: (shortCode: string) =>
    request<{ status: string; event_title: string }>('POST', `/api/attendance/checkin/${shortCode}`),

  listSecurity: (eventId: string) =>
    request<SecurityAssignmentDto[]>('GET', `/api/events/${eventId}/security`),
  assignSecurity: (eventId: string, memberId: string) =>
    request<SecurityAssignmentDto>('POST', `/api/events/${eventId}/security`, { member_id: memberId }),
  removeSecurity: (eventId: string, taskId: string) =>
    request<void>('DELETE', `/api/events/${eventId}/security/${taskId}`),
  requestSwap: (eventId: string, taskId: string, targetMemberId: string, note?: string) =>
    request<SwapDto>('POST', `/api/events/${eventId}/security/${taskId}/swap-request`, {
      target_member_id: targetMemberId,
      note: note || null
    }),
  acceptSwap: (eventId: string, swapId: string) =>
    request<SwapDto>('POST', `/api/events/${eventId}/security/swaps/${swapId}/accept`, {}),
  declineSwap: (eventId: string, swapId: string) =>
    request<SwapDto>('POST', `/api/events/${eventId}/security/swaps/${swapId}/decline`, {}),
  cancelSwap: (eventId: string, swapId: string) =>
    request<SwapDto>('POST', `/api/events/${eventId}/security/swaps/${swapId}/cancel`, {}),

  getExcuses: () => request<ExcuseDto[]>('GET', '/api/excuses/'),
  submitExcuse: (eventId: string, reason: string) =>
    request<ExcuseDto>('POST', `/api/excuses/event/${eventId}`, { reason }),
  reviewExcuse: (id: string, status: 'approved' | 'denied') =>
    request<ExcuseDto>('PUT', `/api/excuses/${id}/review`, { status }),

  markAttendance: (eventId: string, memberId: string, status: 'present' | 'excused' | 'absent') =>
    request<unknown>('POST', `/api/attendance/event/${eventId}/manual/${memberId}`, { status }),

  getFines: () => request<FineDto[]>('GET', '/api/fines/'),
  issueFines: (eventId: string, memberIds: string[]) =>
    request<unknown>('POST', '/api/fines/issue', { event_id: eventId, member_ids: memberIds }),

  getTreasuryDashboard: () => request<TreasuryDashboardDto>('GET', '/api/treasury/dashboard'),

  getTasks: () => request<TaskDto[]>('GET', '/api/tasks/'),
  createTask: (body: Record<string, unknown>) => request<TaskDto>('POST', '/api/tasks/', body),
  setTaskStatus: (id: string, status: string) =>
    request<TaskDto>('POST', `/api/tasks/${id}/status`, { status }),
  commitTask: (id: string, memberId?: string) =>
    request<void>('POST', `/api/tasks/${id}/commit`, { member_id: memberId }),
  uncommitTask: (id: string) => request<void>('POST', `/api/tasks/${id}/uncommit`, {}),

  createJob: (body: {
    title: string;
    description?: string;
    people_needed: number;
    event_id?: string;
    initiative_id?: string;
  }) => request<TaskDto>('POST', '/api/tasks/', body),
  updateJob: (id: string, body: { title?: string; description?: string; people_needed?: number }) =>
    request<void>('PATCH', `/api/tasks/${id}`, body),
  deleteJob: (id: string) => request<void>('DELETE', `/api/tasks/${id}`),
  reportJobDone: (id: string) => request<void>('POST', `/api/tasks/${id}/report-done`, {}),
  approveJob: (id: string) => request<void>('POST', `/api/tasks/${id}/approve`, {}),
  rejectJob: (id: string, reason: string) =>
    request<void>('POST', `/api/tasks/${id}/reject`, { reason }),

  getAnnouncements: () => request<AnnouncementDto[]>('GET', '/api/announcements/'),
  // calendar_time without calendar_date is a 422 — only send it with a date.
  createAnnouncement: (body: {
    title: string;
    body: string;
    calendar_date?: string;
    calendar_time?: string;
  }) => request<AnnouncementDto>('POST', '/api/announcements/', body),
  sendAnnouncement: (id: string) => request<void>('POST', `/api/announcements/${id}/send`),
  /** Draft -> deleted, sent -> hidden from the calendar. Idempotent. */
  deleteAnnouncement: (id: string) => request<void>('DELETE', `/api/announcements/${id}`),

  getRecruits: () => request<RecruitDto[]>('GET', '/api/recruitment/recruits'),
  createRecruit: (body: Record<string, unknown>) =>
    request<RecruitDto>('POST', '/api/recruitment/recruits', body),
  setRecruitStage: (id: string, stage: string) =>
    request<RecruitDto>('POST', `/api/recruitment/recruits/${id}/stage`, { stage }),

  getInitiatives: () => request<InitiativeDto[]>('GET', '/api/initiatives/'),
  createInitiative: (body: Record<string, unknown>) =>
    request<InitiativeDto>('POST', '/api/initiatives/', body)
};

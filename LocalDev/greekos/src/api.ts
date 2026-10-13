// Thin fetch client for the real GuildOS FastAPI backend.
// Vite proxies /api -> http://localhost:8001 (see vite.config.ts).
// Deployed Vercel 404s /api/auth/dev-login; production login is email+password.

const TOKEN_KEY = 'g_token';
const DEV_EMAIL = 'jake@tke.org';

export class AuthRequiredError extends Error {
  constructor() {
    super('Sign in required');
    this.name = 'AuthRequiredError';
  }
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/** Every auth endpoint answers with a session; `password_setup_required` (redeem
 *  only) means the member must set a password before anything else. */
export interface AuthResponse { access_token: string; password_setup_required?: boolean }

/** POSTs to an auth endpoint and stores the returned session token.
 *  Errors carry `status` and, for the 403 password-required reveal, `code`. */
async function authPost(path: string, body: unknown, withToken = false): Promise<AuthResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (withToken) headers.Authorization = `Bearer ${localStorage.getItem(TOKEN_KEY) ?? ''}`;

  let res: Response;
  try {
    res = await fetch(path, { method: 'POST', headers, body: JSON.stringify(body) });
  } catch {
    throw Object.assign(new Error('Network request failed'), { status: 0 });
  }

  const text = await res.text();
  let parsed: { detail?: unknown; message?: string } | undefined;
  try { parsed = text ? JSON.parse(text) : undefined; } catch { /* non-JSON */ }

  if (!res.ok) {
    const detail = parsed?.detail;
    const asObject = (detail && typeof detail === 'object' ? detail : {}) as { message?: string; code?: string };
    const message = typeof detail === 'string' ? detail : (asObject.message || parsed?.message || text);
    throw Object.assign(new Error(message || `Request failed (${res.status})`), {
      status: res.status,
      code: asObject.code
    });
  }

  const data = parsed as unknown as AuthResponse | undefined;
  if (!data?.access_token) {
    throw Object.assign(new Error('Malformed auth response'), { status: res.status });
  }
  localStorage.setItem(TOKEN_KEY, data.access_token);
  return data;
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return authPost('/api/auth/login', { email: email.trim().toLowerCase(), password });
}

/** Invite setup codes and officer-issued reset codes redeem through the same door. */
export function redeemSetupCode(email: string, code: string): Promise<AuthResponse> {
  return authPost('/api/auth/redeem-setup-code', { email: email.trim().toLowerCase(), code });
}

/** Sends the setup-only token from redeem-setup-code; the response is a full session token. */
export function setPassword(password: string): Promise<AuthResponse> {
  return authPost('/api/auth/set-password', { password }, true);
}

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

/** Local `vite` only — Vercel builds are production and must use password login. */
export async function localDevLogin(): Promise<string> {
  if (!import.meta.env.DEV) throw new AuthRequiredError();
  return devLogin();
}

// ----------------------------------------------------
// CHAPTER ONBOARDING (pre-login: no token, by design)
// ----------------------------------------------------
export interface CreateChapterResult {
  chapter_id: string;
  officer_id: string;
  officer_email: string;
  setup_code: string;
  setup_code_expires_at: string;
}

/** POST /api/chapters — the bootstrap path, so deliberately unauthenticated.
 *  Rate-limited server side; a 429 here means "try again later", not a bug. */
export async function createChapter(body: {
  name: string;
  organization?: string;
  school?: string;
  officer_name: string;
  officer_email: string;
  officer_phone: string;
  /** Did the officer tick the SMS opt-in? Absent means no (#57). */
  sms_consent?: boolean;
}): Promise<CreateChapterResult> {
  const res = await fetch('/api/chapters', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, officer_email: body.officer_email.trim().toLowerCase() })
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      const parsed = JSON.parse(text);
      detail = typeof parsed.detail === 'string'
        ? parsed.detail
        : (parsed.detail?.[0]?.msg || parsed.detail?.message || text);
    } catch { /* non-JSON */ }
    throw new Error(detail || `Could not create the chapter (${res.status})`);
  }
  return JSON.parse(text) as CreateChapterResult;
}

export interface RosterRowError { row: number; error: string; }

export interface RosterImportResult {
  created: { email: string; setup_code: string }[];
  skipped: string[];
  created_count: number;
  skipped_count: number;
}

/** A rejected roster file: every row that failed, nothing imported. */
export class RosterRejectedError extends Error {
  constructor(public rows: RosterRowError[]) {
    super('No members were imported');
    this.name = 'RosterRejectedError';
  }
}

export async function ensureLogin(): Promise<string> {
  const existing = localStorage.getItem(TOKEN_KEY);
  if (existing) return existing;
  throw new AuthRequiredError();
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  retry = true,
  headers?: Record<string, string>
): Promise<T> {
  const token = await ensureLogin();
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...headers },
    body: body === undefined ? undefined : JSON.stringify(body)
  });

  if (res.status === 401 && retry) {
    localStorage.removeItem(TOKEN_KEY);
    throw new AuthRequiredError();
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

/** Multipart upload. Separate from `request` only because the body is a
 *  FormData (the browser must set its own Content-Type boundary). */
async function uploadRoster(chapterId: string, file: File): Promise<RosterImportResult> {
  const token = await ensureLogin();
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`/api/chapters/${chapterId}/roster`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form
  });

  if (res.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    throw new AuthRequiredError();
  }

  const text = await res.text();
  if (!res.ok) {
    let detail: unknown = text;
    try { detail = JSON.parse(text).detail; } catch { /* non-JSON */ }
    const rows = (detail as { errors?: RosterRowError[] })?.errors;
    if (rows) throw new RosterRejectedError(rows);
    throw new Error(typeof detail === 'string' ? detail : `Upload failed (${res.status})`);
  }
  return JSON.parse(text) as RosterImportResult;
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
export interface MeDto { id: string; name: string; email: string; role: string; chapter_id: string; chapter_name: string | null; }

/** GET /api/rbac/me/permissions — the only source of authority in the UI. */
export interface MyPermissionsDto { permissions: string[]; roles: string[]; }

/** GET /api/rbac/roles — the assignable role catalog. */
export interface RoleDto { key: string; label: string; }
export interface MemberRoleDto { role_key: string; }

export interface MemberDto {
  id: string;
  name: string;
  email: string;
  role: string;
  status: string;
  /** May we text them? (#57) Absent on an older backend, which means no. */
  sms_consent?: boolean;
}

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

/** Check-in link. GET answers `{}` when no link is live; a member who cannot
 *  manage check-in gets `{event_id, active, expires_at}` with no code. */
export interface CheckInLinkDto {
  event_id?: string;
  active?: boolean;
  short_code?: string;
  url?: string;
  expires_at?: string;
}

export interface NotifyPreviewDto {
  recipient_count: number;
  no_phone_count: number;
  /** Members with a phone but no SMS consent — dropped from the blast (#89). */
  no_consent_count: number;
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

/** GET /api/events/upcoming-details — what GET /api/events/{id}, /security and
 *  /checkin-link return, for every upcoming event, in one request. */
export interface UpcomingDetailsDto {
  events: {
    event_id: string;
    detail: EventDetailDto;
    security: SecurityAssignmentDto[];
    checkin_link: CheckInLinkDto;
  }[];
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
  /** What is still owed after payment allocations; 0 once paid or waived. */
  remaining_cents: number;
  status: string;
  reason: string;
  issued_at: string | null;
  member_id: string | null;
  member_name: string | null;
  event_id: string | null;
  event_title: string | null;
  event_date: string | null;
}

/** POST /api/fines/issue — who got the flat fine and who was skipped
 *  (present, excused, or already fined for that event). */
export interface IssueFinesResultDto {
  event_id: string;
  flat_fine_cents: number;
  issued_member_ids: string[];
  skipped_member_ids: string[];
}

export interface VerifiedPaymentDto {
  id: string;
  /** Reference recorded by the officer or payment proof. */
  proof_ref?: string | null;
  member_id: string;
  /** Always null since coverage moved to payment_allocations. */
  invoice_id: string | null;
  amount_cents: number;
  /** venmo|zelle|cash|bank_transfer|check. ponytail: the dashboard does not
   *  join it from payment_submissions yet, so rows render "—" until it does. */
  method?: string | null;
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

/** One open invoice as the member dashboard presents it. `source` is the V1
 *  vocabulary (dues|fine|manual|…), `status` the V1 open/paid/void mapping. */
export interface OpenInvoiceDto {
  id: string;
  description: string | null;
  amount_cents: number;
  remaining_cents: number;
  due_at: string | null;
  overdue: boolean;
  source: string | null;
  status: string;
}

/** Evidence metadata, as the review queue carries it (never the bytes). */
export interface EvidenceRefDto {
  id: string;
  content_type: string;
  size_bytes: number;
}

/** A member's claim that they paid, awaiting a `treasury:payment:verify` holder. */
export interface PaymentSubmissionDto {
  id: string;
  member_id: string;
  invoice_id: string | null;
  claimed_amount_cents: number;
  method: string;
  status: string;
  proof_ref: string | null;
  created_at: string;
  /** Present on the review-queue read; absent on a freshly-created submission. */
  evidence?: EvidenceRefDto[];
}

/** GET /api/treasury/payments/evidence/{id} — the bytes, base64-encoded. */
export interface EvidenceDto extends EvidenceRefDto {
  submission_id: string;
  data_base64: string;
}

export interface BulkInvoiceResultDto { count: number; invoice_ids: string[]; }

export interface PageDto<T> { data: T[]; next_cursor: string | null; total: number; }

/** GET /api/treasury/members/{id}/dashboard — readable by the member themself. */
export interface MemberTreasuryDashboardDto {
  member_id: string;
  balance: {
    outstanding_balance_cents: number;
    current_balance_cents: number;
    total_owed_cents: number;
    total_paid_cents: number;
  };
  pending_cents: number;
  pending_submissions: PaymentSubmissionDto[];
  open_invoices: OpenInvoiceDto[];
  recent_activity: unknown[];
}

/** POST /api/treasury/invoices — one invoice in the V1 shape. */
export interface InvoiceDto {
  id: string;
  member_id: string;
  kind: string;
  amount_cents: number;
  description: string | null;
  status: string;
}

/** POST /api/treasury/adjustments. `pending` means the amount is at or over
 *  the second-sign-off threshold and has not applied yet. */
export interface AdjustmentDto {
  id: string;
  member_id: string | null;
  kind: string;
  delta_cents: number;
  reason: string;
  status: string;
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

/** GET /api/announcements/outbox — one message_outbox row (issue #48). */
export interface OutboxMessageDto {
  id: string;
  event_type: string;
  recipient_name: string | null;
  recipient_phone: string | null; // masked to the last four digits
  channel?: string; // email | sms; absent on an older backend, which only sent SMS
  body: string;
  status: string; // pending | sending | sent | failed | simulated
  attempts: number;
  created_at: string;
  delivered_at: string | null;
  error: string | null;
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

/** GET /api/contribution/me — the member's own derived record (issue #40). */
export interface ContributionDto {
  member_id: string;
  events_organized: { event_id: string; title: string; date: string; attendee_count: number }[];
  events_supervised: { event_id: string; title: string; date: string; attendee_count: number }[];
  initiatives_chaired: {
    initiative_id: string;
    title: string;
    date_range: { start: string; end: string | null };
  }[];
  jobs_done: {
    job_id: string;
    title: string;
    attached_to: 'event' | 'initiative' | 'standalone';
    date: string;
  }[];
  events_attended_count: number;
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
  getMyPermissions: () => request<MyPermissionsDto>('GET', '/api/rbac/me/permissions'),

  // Role assignment — all four need the caller's `roles:assign` permission
  // except the catalog, which any member may read.
  getRoleCatalog: () => request<RoleDto[]>('GET', '/api/rbac/roles'),
  getMemberRoles: (memberId: string) =>
    request<MemberRoleDto[]>('GET', `/api/rbac/members/${memberId}/roles`),
  assignMemberRole: (memberId: string, roleKey: string) =>
    request<unknown>('POST', `/api/rbac/members/${memberId}/roles`, { role_key: roleKey }),
  revokeMemberRole: (memberId: string, roleKey: string) =>
    request<unknown>('DELETE', `/api/rbac/members/${memberId}/roles/${roleKey}`),

  getMembers: () => request<MemberDto[]>('GET', '/api/members/'),
  /** Officer-only. Rejects the whole file (RosterRejectedError) if any row is bad. */
  importRoster: (chapterId: string, file: File) => uploadRoster(chapterId, file),
  getStandings: () => request<StandingDto[]>('GET', '/api/standing/'),
  // Officer-gated (STANDING_VIEW_ALL): callers must tolerate a 403.
  getScores: () => request<ScoreDto[]>('GET', '/api/memberadmin/scores'),

  getEvents: () => request<EventDto[]>('GET', '/api/events/'),
  getEvent: (id: string) => request<EventDetailDto>('GET', `/api/events/${id}`),
  getUpcomingEventDetails: () => request<UpcomingDetailsDto>('GET', '/api/events/upcoming-details'),
  createEvent: (body: Record<string, unknown>) => request<EventDto>('POST', '/api/events/', body),
  updateEvent: (id: string, body: Record<string, unknown>) =>
    request<EventDto>('PUT', `/api/events/${id}`, body),
  /** An event with attendance, jobs or fines is cancelled rather than deleted. */
  deleteEvent: (id: string) =>
    request<{ deleted: boolean; cancelled: boolean }>('DELETE', `/api/events/${id}`),

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
  getFineEligibility: (eventId: string) =>
    request<{ event_start: string }>('GET', `/api/fines/missed/${eventId}`),
  issueFines: (eventId: string, memberIds: string[]) =>
    request<unknown>('POST', '/api/fines/issue', { event_id: eventId, member_ids: memberIds }),

  getTreasuryDashboard: () => request<TreasuryDashboardDto>('GET', '/api/treasury/dashboard'),
  getMemberTreasuryDashboard: (memberId: string) =>
    request<MemberTreasuryDashboardDto>('GET', `/api/treasury/members/${memberId}/dashboard`),

  // ── The dues run → invoice → proof → verify loop ────────────────────────────
  /** One dues run = one bulk batch. Needs `treasury:invoice:create`.
   *  `idempotencyKey` is one key per opened dues-run modal, so a retry after a
   *  timeout cannot bill the chapter twice. */
  bulkCreateInvoices: (invoices: {
    member_id: string;
    kind: string;
    amount_cents: number;
    description?: string;
    due_at?: string;
  }[], idempotencyKey: string) =>
    request<BulkInvoiceResultDto>('POST', '/api/treasury/invoices/bulk', { invoices }, true, {
      'Idempotency-Key': idempotencyKey
    }),

  /** The member's own claim that they paid — self only, no permission key. */
  submitPaymentProof: (body: {
    invoice_id: string;
    claimed_amount_cents: number;
    method: string;
    proof_ref?: string;
  }) => request<PaymentSubmissionDto>('POST', '/api/treasury/payments/submissions', body),

  /** Attach a screenshot to a submission the caller owns (≤ 2 MiB). */
  addPaymentEvidence: (submissionId: string, contentType: string, dataBase64: string) =>
    request<EvidenceRefDto>('POST', `/api/treasury/payments/submissions/${submissionId}/evidence`, {
      content_type: contentType,
      data_base64: dataBase64
    }),

  /** The review queue. Needs `treasury:payment:verify`. */
  listPaymentSubmissions: (status = 'pending') =>
    request<PageDto<PaymentSubmissionDto>>(
      'GET',
      `/api/treasury/payments/submissions?status=${encodeURIComponent(status)}`
    ),

  /** Evidence bytes — the reviewer or the submitting member. */
  getPaymentEvidence: (evidenceId: string) =>
    request<EvidenceDto>('GET', `/api/treasury/payments/evidence/${evidenceId}`),

  // The -v1 pair is the current path: verify allocates oldest-first across the
  // member's open invoices, and reject makes the reason mandatory.
  verifyPaymentSubmission: (submissionId: string) =>
    request<unknown>('POST', `/api/treasury/payments/submissions/${submissionId}/verify-v1`),
  rejectPaymentSubmission: (submissionId: string, reason: string) =>
    request<unknown>('POST', `/api/treasury/payments/submissions/${submissionId}/reject-v1`, { reason }),

  // ── Officer-recorded transactions. Every one carries an Idempotency-Key the
  // form regenerates when its values change, so a retry never doubles up. ──────
  /** Record and verify a payment the officer received, in one step (D1).
   *  Needs `treasury:payment:verify`. */
  recordPayment: (body: {
    member_id: string;
    amount_cents: number;
    method: string;
    invoice_id: string | null;
    reference: string | null;
  }, idempotencyKey: string) =>
    request<unknown>('POST', '/api/treasury/payments/record', body, true, {
      'Idempotency-Key': idempotencyKey
    }),

  /** One invoice — a free-form fine or a manual charge. Needs `treasury:invoice:create`. */
  createInvoice: (body: {
    member_id: string;
    source: 'fine' | 'manual';
    amount_cents: number;
    description: string;
  }, idempotencyKey: string) =>
    request<InvoiceDto>('POST', '/api/treasury/invoices', body, true, {
      'Idempotency-Key': idempotencyKey
    }),

  /** A signed correction. Needs `treasury:adjustment:create`; the response's
   *  `status` is `pending` when a second officer has to approve it. */
  createAdjustment: (body: {
    member_id: string;
    kind: 'manual_correction';
    delta_cents: number;
    reason: string;
  }, idempotencyKey: string) =>
    request<AdjustmentDto>('POST', '/api/treasury/adjustments', body, true, {
      'Idempotency-Key': idempotencyKey
    }),

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

  getOutbox: (status?: string) =>
    request<OutboxMessageDto[]>(
      'GET',
      `/api/announcements/outbox${status ? `?status=${encodeURIComponent(status)}` : ''}`
    ),
  /** Failed -> pending; the next cron drain re-sends it. 409 on any other status. */
  retryOutboxMessage: (id: string) =>
    request<void>('POST', `/api/announcements/outbox/${id}/retry`, {}),

  /** The signed-in member opting themselves in to SMS; also clears any STOP. */
  optInToSms: () => request<void>('POST', '/api/members/me/sms-consent', {}),


  getMyContribution: () => request<ContributionDto>('GET', '/api/contribution/me'),

  getInitiatives: () => request<InitiativeDto[]>('GET', '/api/initiatives/'),
  createInitiative: (body: Record<string, unknown>) =>
    request<InitiativeDto>('POST', '/api/initiatives/', body)
};

import type { CheckInLinkDto } from './api';
// Backend DTO -> prototype type mapping. Everything the backend does not send
// gets an empty default here — nothing is invented. Client-local demo features
// (GPA, pledge class) stay defaulted.
import {
  AnnouncementDto,
  ContributionDto,
  EventDetailDto,
  EventDto,
  ExcuseDto,
  FineDto,
  InitiativeDto,
  MemberDto,
  OutboxMessageDto,
  RecruitDto,
  ScoreDto,
  SecurityAssignmentDto,
  StandingDto,
  TaskDto,
  UpcomingDetailsDto,
  VerifiedPaymentDto
} from './api';
import {
  Announcement,
  ChapterEvent,
  Excuse,
  EventJob,
  EventType,
  Fine,
  Initiative,
  Member,
  MemberRole,
  MemberStanding,
  OutboxMessage,
  OutboxStatus,
  Payment,
  PNM,
  SecurityAssignment,
  Task
} from './types';
import { ContributionRecord } from './lib/contribution';
import { PAYMENT_METHODS } from './lib/dues';

const nameOf = (members: Member[], id: string | null | undefined) =>
  members.find(m => m.id === id)?.name || 'Unknown Member';

const day = (value: string | null | undefined) => (value || '').substring(0, 10);

const hhmm = (value: string | null | undefined) => (value || '').substring(0, 5);

// ----------------------------------------------------
// MEMBERS (roster + standing merged; standing carries dues + attendance)
// ----------------------------------------------------
const STANDINGS: Record<string, MemberStanding> = {
  good_standing: 'Good Standing',
  warning: 'Financial Probation',
  delinquent: 'Financial Hold'
};

/** `scores` is officer-only; it arrives empty for a member session, which just
 *  leaves every prior-shift count at 0. */
export function adaptMembers(
  rows: MemberDto[],
  standings: StandingDto[],
  scores: ScoreDto[] = []
): Member[] {
  const byId = new Map(standings.map(s => [s.member_id, s]));
  const shiftsById = new Map(scores.map(s => [s.member_id, s.prior_security_shifts]));
  return rows.map(row => {
    const s = byId.get(row.id);
    const balanceCents = s ? s.unpaid_amount_cents : 0;
    const role: MemberRole = row.role === 'officer' ? 'Officer' : 'Active Member';
    return {
      id: row.id,
      name: row.name,
      email: row.email,
      phone: '',
      role: row.status === 'alumni' ? 'Alumni' : role,
      status: row.status === 'alumni' ? 'Alumni' : row.status === 'active' ? 'Active' : 'Inactive',
      standing: (s && STANDINGS[s.standing]) || 'Good Standing',
      gpa: 0,
      duesBalanceCents: balanceCents,
      duesBalance: balanceCents / 100,
      attendanceRate: s && s.total_required ? Math.round((s.attended / s.total_required) * 100) : 0,
      pledgeClass: '',
      securityHoursServed: 0,
      priorSecurityShifts: shiftsById.get(row.id) || 0,
      smsConsent: row.sms_consent === true
    };
  });
}

// ----------------------------------------------------
// EVENTS
// ----------------------------------------------------
const EVENT_TYPES: EventType[] = [
  'Chapter Meeting',
  'Philanthropy',
  'Brotherhood',
  'Social',
  'Recruitment',
  'Pledge Education',
  'Community Service'
];

const toEventType = (raw: string | null | undefined): EventType =>
  EVENT_TYPES.find(t => t.toLowerCase() === (raw || '').trim().toLowerCase()) || 'Chapter Meeting';

export function adaptEvents(rows: EventDto[]): ChapterEvent[] {
  return rows.map(row => {
    const startTime = hhmm(row.time);
    const endTime = hhmm(row.end_time);
    return {
      id: row.id,
      title: row.title,
      description: row.description || '',
      date: day(row.date),
      startTime,
      endTime,
      time: endTime ? `${startTime} - ${endTime}` : startTime,
      location: row.location || '',
      type: toEventType(row.event_type),
      audience: row.visibility === 'officer' ? 'Officers Only' : 'All Members',
      required: !!row.required,
      attendanceTaken: false,
      checkedInCount: row.attendance_count || 0,
      jobCount: row.job_count || 0,
      openJobCount: row.open_job_count || 0,
      // The list carries the organizer count but no names; names arrive with
      // the per-event detail (adaptEventDetail).
      organizerCount: row.organizer_count || 0,
      supervisors: [],
      organizers: [],
      jobs: [],
      securityAssignments: []
    };
  });
}

/** The fields only GET /api/events/{id} carries, as a patch onto the list row.
 *  Supervisor rows ship a name; organizer rows carry ids only, so those are
 *  resolved off the roster the way adaptSecurityAssignment does. */
export function adaptEventDetail(dto: EventDetailDto, members: Member[]): Partial<ChapterEvent> {
  return {
    supervisors: (dto.supervisors || []).map(s => s.name || nameOf(members, s.member_id)),
    organizers: (dto.organizers || []).map(o => nameOf(members, o.member_id)),
    organizerCount: (dto.organizers || []).length,
    checkedInCount: dto.attendance_count || 0,
    notifiedAt: dto.last_notified_at || undefined
  };
}

/** Security assignment row -> shift card. The backend models a shift as a task
 *  commitment (`task_id`) with at most one pending swap; it has no station. */
export function adaptSecurityAssignment(
  dto: SecurityAssignmentDto,
  membersById: Map<string, Member>
): SecurityAssignment {
  const swap = dto.pending_swap && dto.pending_swap.status === 'pending' ? dto.pending_swap : null;
  const memberId = dto.member_id || '';
  return {
    id: dto.task_id,
    memberId,
    memberName: membersById.get(memberId)?.name || 'Unknown Member',
    station: '',
    status: 'Confirmed',
    swapRequestedWithId: swap ? swap.target_member_id : undefined,
    swapRequestedWithName: swap
      ? membersById.get(swap.target_member_id)?.name || 'Unknown Member'
      : undefined,
    swapStatus: swap ? 'Pending' : undefined
  };
}

/** GET /api/events/upcoming-details -> the per-event security shifts and the
 *  detail-only fields (leaders, counts, door code) keyed by event id. */
export function adaptUpcomingDetails(
  dto: UpcomingDetailsDto,
  members: Member[],
  membersById: Map<string, Member>
) {
  const securityByEvent = new Map<string, SecurityAssignment[]>();
  const detailByEvent = new Map<string, Partial<ChapterEvent>>();
  for (const row of dto.events) {
    securityByEvent.set(row.event_id, row.security.map(s => adaptSecurityAssignment(s, membersById)));
    detailByEvent.set(row.event_id, { ...adaptEventDetail(row.detail, members), ...adaptCheckInLink(row.checkin_link) });
  }
  return { securityByEvent, detailByEvent };
}

/** ChapterEvent -> EventCreate/EventUpdate body. */
export function toEventBody(event: {
  title: string;
  description?: string;
  date: string;
  startTime: string;
  endTime: string;
  location: string;
  type: EventType;
  audience: string;
  required: boolean;
}): Record<string, unknown> {
  return {
    title: event.title,
    description: event.description || null,
    date: event.date,
    time: event.startTime,
    end_time: event.endTime || null,
    location: event.location,
    required: event.required,
    event_type_name: event.type,
    audience: event.audience === 'Officers Only' ? 'officers' : 'all'
  };
}

// ----------------------------------------------------
// EXCUSES
// ----------------------------------------------------
export function adaptExcuses(rows: ExcuseDto[], members: Member[]): Excuse[] {
  return rows.map(row => ({
    id: row.id,
    memberId: row.member_id,
    memberName: row.members?.name || nameOf(members, row.member_id),
    eventId: row.event_id,
    eventName: row.events?.title || 'Chapter Event',
    eventTitle: row.events?.title || 'Chapter Event',
    eventDate: day(row.events?.date),
    reason: row.reason,
    status: row.status === 'approved' ? 'Approved' : row.status === 'denied' ? 'Rejected' : 'Pending',
    submittedAt: (row.submitted_at || '').replace('T', ' ').substring(0, 16)
  }));
}

// ----------------------------------------------------
// FINANCE (fines from /api/fines, payments from the treasury dashboard)
// ----------------------------------------------------
export function adaptFines(rows: FineDto[], members: Member[]): Fine[] {
  return rows.map(row => ({
    id: row.id,
    memberId: row.member_id || '',
    memberName: row.member_name || nameOf(members, row.member_id),
    amountCents: row.amount_cents,
    remainingCents: row.remaining_cents,
    amount: row.amount_cents / 100,
    reason: row.reason || 'Fine',
    date: day(row.issued_at),
    // 'cancelled' is a waived fine: no longer owed, but nobody paid it either.
    status: row.status === 'unpaid' || row.status === 'partially_paid' ? 'Unpaid'
      : row.status === 'cancelled' ? 'Waived' : 'Paid',
    relatedEventId: row.event_id || undefined
  }));
}

export function adaptPayments(rows: VerifiedPaymentDto[], members: Member[]): Payment[] {
  return rows.map(row => ({
    id: row.id,
    memberId: row.member_id,
    memberName: nameOf(members, row.member_id),
    amountCents: row.amount_cents,
    amount: row.amount_cents / 100,
    date: day(row.verified_at || row.created_at),
    // A dash, never a made-up method, when the row does not say.
    paymentMethod: PAYMENT_METHODS.find(m => m.value === row.method)?.label ?? row.method ?? '—',
    reference: row.invoice_id ?? undefined
  }));
}

// ----------------------------------------------------
// TASKS
// ----------------------------------------------------
const TASK_STATUS: Record<string, Task['status']> = {
  open: 'To Do',
  committed: 'Pending',
  in_progress: 'In Progress',
  done: 'Completed',
  done_reported: 'Done Reported',
  approved: 'Approved',
  cancelled: 'Cancelled'
};

export function adaptTasks(
  rows: TaskDto[],
  members: Member[],
  titles: { events?: Map<string, string>; initiatives?: Map<string, string> } = {}
): Task[] {
  // Security shifts live on the event's Security panel, never on the jobs board.
  return rows.filter(row => row.kind !== 'security').map(row => ({
    id: row.id,
    title: row.title,
    description: row.description || '',
    assignedTo: row.claimants?.length
      ? row.claimants.map(id => nameOf(members, id)).join(', ')
      : row.assigned_member_id ? nameOf(members, row.assigned_member_id) : 'Unassigned',
    assignedToId: row.assigned_member_id || undefined,
    claimants: (row.claimants ?? []).map(memberId => ({ memberId, memberName: nameOf(members, memberId), claimedAt: '' })),
    peopleNeeded: row.people_needed ?? 1,
    claimedCount: row.claimed_count ?? row.claimants?.length ?? 0,
    dueDate: day(row.due_at),
    priority: row.required ? 'High' : 'Medium',
    status: TASK_STATUS[row.status] || 'Unknown',
    parent: row.event_id
      ? { kind: 'event', title: titles.events?.get(row.event_id) || 'Event' }
      : row.initiative_id
        ? { kind: 'initiative', title: titles.initiatives?.get(row.initiative_id) || 'Initiative' }
        : undefined
  }));
}

// ----------------------------------------------------
// JOBS (the same tasks rows, viewed as event/initiative jobs)
// ----------------------------------------------------
const JOB_STATUS: Record<string, EventJob['status']> = {
  open: 'To Do',
  in_progress: 'In Progress',
  done_reported: 'Done Reported',
  approved: 'Approved'
};

export function adaptTaskToJob(t: TaskDto, membersById: Map<string, Member>): EventJob {
  return {
    id: t.id,
    title: t.title,
    description: t.description ?? '',
    peopleNeeded: t.people_needed ?? 1,
    // The commitment summary carries ids only — no claim timestamp is exposed.
    claimants: (t.claimants ?? []).map(id => ({
      memberId: id,
      memberName: membersById.get(id)?.name ?? 'Unknown',
      claimedAt: ''
    })),
    status: JOB_STATUS[t.status] ?? 'To Do',
    rejectionReason: t.rejection_reason ?? undefined,
    isSecurity: t.kind === 'security'
  };
}

/** Split job rows by parent. Cancelled jobs and security jobs never show on a
 *  jobs board (security has its own screen), so both are dropped here. */
export function groupJobsByParent(tasks: TaskDto[], membersById: Map<string, Member>) {
  const byEvent = new Map<string, EventJob[]>();
  const byInitiative = new Map<string, EventJob[]>();
  const push = (map: Map<string, EventJob[]>, key: string, job: EventJob) => {
    const list = map.get(key);
    if (list) list.push(job);
    else map.set(key, [job]);
  };
  for (const t of tasks) {
    if (t.status === 'cancelled' || t.kind === 'security') continue;
    const job = adaptTaskToJob(t, membersById);
    if (t.event_id) push(byEvent, t.event_id, job);
    else if (t.initiative_id) push(byInitiative, t.initiative_id, job);
  }
  return { byEvent, byInitiative };
}

// ----------------------------------------------------
// ANNOUNCEMENTS
// ----------------------------------------------------
export function adaptAnnouncements(rows: AnnouncementDto[], members: Member[]): Announcement[] {
  // A retired (deleted) announcement stays in the backend feed but is off the
  // calendar — the prototype only surfaces announcements as calendar items.
  return rows.filter(row => !row.hidden_from_calendar).map(row => ({
    id: row.id,
    title: row.title,
    content: row.body,
    author: row.created_by ? nameOf(members, row.created_by) : 'Chapter',
    date: day(row.sent_at || row.created_at),
    priority: 'Normal',
    channels: ['Calendar'],
    calendarDate: day(row.calendar_date) || undefined,
    calendarTime: hhmm(row.calendar_time) || undefined
  }));
}

// ----------------------------------------------------
// RECRUITMENT
// ----------------------------------------------------
const RECRUIT_STAGES: Record<string, PNM['status']> = {
  lead: 'Lead',
  contacted: 'Contacted',
  attended_event: 'Invited to House',
  bid_extended: 'Bid Extended',
  bid_accepted: 'Bid Accepted',
  dropped: 'Declined'
};

export function adaptRecruits(rows: RecruitDto[]): PNM[] {
  return rows.map(row => ({
    id: row.id,
    name: row.name,
    hometown: '',
    major: '',
    phone: row.phone || '',
    email: row.email || undefined,
    status: RECRUIT_STAGES[row.stage] || 'Prospect',
    notes: row.notes || undefined,
    votesFor: 0,
    votesAgainst: 0
  }));
}

// ----------------------------------------------------
// OUTBOX
// ----------------------------------------------------
export function adaptOutbox(rows: OutboxMessageDto[]): OutboxMessage[] {
  return rows.map(row => ({
    id: row.id,
    eventType: row.event_type,
    recipientName: row.recipient_name || 'Chapter-wide',
    recipientPhone: row.recipient_phone || '',
    channel: row.channel === 'email' ? 'email' : 'sms',
    body: row.body,
    status: row.status as OutboxStatus,
    attempts: row.attempts,
    createdAt: row.created_at,
    deliveredAt: row.delivered_at || undefined,
    error: row.error || undefined
  }));
}

// ----------------------------------------------------
// INITIATIVES
// ----------------------------------------------------
export function adaptInitiatives(rows: InitiativeDto[], members: Member[]): Initiative[] {
  return rows.map(row => ({
    id: row.id,
    title: row.title,
    description: row.description || '',
    leadChairs: (row.chair_member_ids || []).map(id => nameOf(members, id)),
    // The backend has no initiative category or lifecycle status yet.
    category: 'Philanthropy',
    startDate: day(row.date),
    targetDate: day(row.end_date || row.date),
    status: 'Active',
    jobs: []
  }));
}

// ----------------------------------------------------
// CONTRIBUTION (issue #40 — the member's own derived record)
// ----------------------------------------------------
export function adaptContribution(row: ContributionDto): ContributionRecord {
  const events = (rows: ContributionDto['events_organized']) =>
    rows.map(e => ({
      eventId: e.event_id,
      title: e.title,
      date: day(e.date),
      attendeeCount: e.attendee_count
    }));
  return {
    eventsOrganized: events(row.events_organized),
    eventsSupervised: events(row.events_supervised),
    initiativesChaired: row.initiatives_chaired.map(i => ({
      initiativeId: i.initiative_id,
      title: i.title,
      start: day(i.date_range.start),
      end: i.date_range.end ? day(i.date_range.end) : null
    })),
    jobsDone: row.jobs_done.map(j => ({
      jobId: j.job_id,
      title: j.title,
      attachedTo: j.attached_to,
      date: day(j.date)
    })),
    eventsAttendedCount: row.events_attended_count
  };
}

/** GET /api/events/{id}/checkin-link: `{}` when no door is open. Managers get
 *  the code; members only learn that a door is open and when it closes. */
export function adaptCheckInLink(dto: CheckInLinkDto): Pick<ChapterEvent, 'checkInLinkActive' | 'checkInToken'> {
  return { checkInLinkActive: dto.active ?? !!dto.short_code, checkInToken: dto.short_code };
}

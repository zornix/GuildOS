// Backend DTO -> prototype type mapping. Everything the backend does not send
// gets an empty default here — nothing is invented. Client-local demo features
// (event jobs, security assignments, check-in PINs, points) stay defaulted.
import {
  AnnouncementDto,
  EventDto,
  ExcuseDto,
  FineDto,
  InitiativeDto,
  MemberDto,
  RecruitDto,
  StandingDto,
  TaskDto,
  VerifiedPaymentDto
} from './api';
import {
  Announcement,
  ChapterEvent,
  Excuse,
  EventType,
  Fine,
  Initiative,
  Member,
  MemberRole,
  MemberStanding,
  Payment,
  PNM,
  Task
} from './types';

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

export function adaptMembers(rows: MemberDto[], standings: StandingDto[]): Member[] {
  const byId = new Map(standings.map(s => [s.member_id, s]));
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
      securityHoursServed: 0
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
      points: 0,
      required: !!row.required,
      attendanceTaken: false,
      checkedInCount: row.attendance_count || 0,
      supervisors: [],
      organizers: [],
      jobs: [],
      securityAssignments: []
    };
  });
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
    amount: row.amount_cents / 100,
    reason: row.reason || 'Fine',
    date: day(row.issued_at),
    // 'cancelled' is a waived fine — no longer owed, so it reads as cleared here.
    status: row.status === 'unpaid' || row.status === 'partially_paid' ? 'Unpaid' : 'Paid',
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
    // The backend records a verified payment against an invoice; it carries
    // neither a category nor a method, so both fall back to a neutral default.
    type: 'Dues',
    date: day(row.verified_at || row.created_at),
    paymentMethod: 'Ledger Credit',
    reference: row.invoice_id
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
  cancelled: 'Completed'
};

export function adaptTasks(rows: TaskDto[], members: Member[]): Task[] {
  return rows.map(row => ({
    id: row.id,
    title: row.title,
    description: row.description || '',
    assignedTo: row.assigned_member_id ? nameOf(members, row.assigned_member_id) : 'Unassigned',
    assignedToId: row.assigned_member_id || undefined,
    dueDate: day(row.due_at),
    priority: row.required ? 'High' : 'Medium',
    status: TASK_STATUS[row.status] || 'To Do'
  }));
}

// ----------------------------------------------------
// ANNOUNCEMENTS
// ----------------------------------------------------
export function adaptAnnouncements(rows: AnnouncementDto[], members: Member[]): Announcement[] {
  return rows.map(row => ({
    id: row.id,
    title: row.title,
    content: row.body,
    author: row.created_by ? nameOf(members, row.created_by) : 'Chapter',
    date: day(row.sent_at || row.created_at),
    priority: 'Normal',
    channels: ['Calendar']
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

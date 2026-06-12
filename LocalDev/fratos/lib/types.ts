export interface Member {
  id: string;
  name: string;
  role: "officer" | "member";
  email: string;
  chapter_id: string;
  status: "active" | "inactive" | "alumni";
}

export interface Event {
  id: string;
  title: string;
  date: string;
  time: string;
  location: string;
  required: boolean;
  fine_amount: number;
  chapter_id: string;
  created_by: string;
  description?: string;
  attendance_count?: number;
}

export interface AttendanceRecord {
  event_id: string;
  member_id: string;
  checked_in: boolean;
  checked_in_at: string | null;
  method: "link" | "manual" | null;
}

export interface RosterEntry {
  member_id: string;
  name: string;
  checked_in: boolean;
  checked_in_at: string | null;
  method: string | null;
  excuse_status: "pending" | "approved" | "denied" | null;
}

export interface Excuse {
  id: string;
  event_id: string;
  member_id: string;
  reason: string;
  status: "pending" | "approved" | "denied";
  reviewed_by: string | null;
  submitted_at: string;
  members?: Pick<Member, "name" | "email">;
  events?: Pick<Event, "title" | "date">;
}

export interface Fine {
  id: string;
  event_id: string;
  member_id: string;
  chapter_id: string;
  amount: number;
  reason: string;
  status: "unpaid" | "paid" | "waived";
  issued_at: string;
  paid_at: string | null;
  waived_by: string | null;
  members?: Pick<Member, "name" | "email">;
  events?: Pick<Event, "title" | "date">;
}

export interface CheckinLink {
  event_id: string;
  short_code: string;
  url: string;
  expires_at: string;
  active: boolean;
  created_by: string;
}

export interface ActiveCheckinLinkRow {
  event_id: string;
  event_title: string;
  date: string;
  short_code: string;
  url: string;
  expires_at: string;
}

export interface FineSummary {
  total_unpaid: number;
  total_paid: number;
  total_waived: number;
  count_unpaid: number;
}

export interface InviteResult {
  invited: string[];
  failed: { email: string; error: string }[];
}

export interface MemberStanding {
  member_id: string;
  name: string;
  email: string;
  standing: "good_standing" | "warning" | "delinquent";
  attended: number;
  total_required: number;
  unexcused_absences: number;
  unpaid_fines: number;
  unpaid_amount: number;
  reason_codes?: string[];
}

// RBAC
export interface MyPermissions {
  permissions: string[];
  roles: string[];
}

export interface RoleCatalogEntry {
  key: string;
  label: string;
}

export interface MemberRole {
  id: string;
  chapter_id: string;
  member_id: string;
  role_key: string;
  assigned_by: string | null;
  assigned_at: string;
}

// Tasks
export type TaskStatus = "open" | "in_progress" | "done" | "cancelled";

export interface Task {
  id: string;
  chapter_id: string;
  group_id: string | null;
  title: string;
  description: string | null;
  assigned_member_id: string | null;
  created_by: string | null;
  status: TaskStatus;
  required: boolean;
  due_at: string | null;
  created_at: string;
}

// Announcements
export type AnnouncementAudience = "chapter" | "officers" | "members_with_balance";

export interface Announcement {
  id: string;
  chapter_id: string;
  title: string;
  body: string;
  audience: AnnouncementAudience;
  status: "draft" | "sent";
  created_by: string | null;
  sent_at: string | null;
  created_at: string;
}

// Recruitment
export type RecruitStage = "lead" | "contacted" | "attended_event" | "bid_extended" | "bid_accepted" | "dropped";

export interface Recruit {
  id: string;
  chapter_id: string;
  name: string;
  email: string | null;
  phone: string | null;
  stage: RecruitStage;
  notes: string | null;
  created_at: string;
}

// Bylaws
export interface BylawsDocument {
  id: string;
  chapter_id: string;
  title: string;
  content: string;
  created_at: string;
}

/** Honest stub contract: `answer` stays null until a real retrieval layer exists. */
export interface BylawsQueryResult {
  status: "not_implemented";
  answer: null;
  question: string;
  documents_available: number;
  detail: string;
}

// NL controller
export type CommandStatus = "pending_approval" | "approved" | "rejected" | "executed" | "failed";

export interface CommandRequest {
  id: string;
  chapter_id: string;
  requested_by: string | null;
  input_text: string;
  proposed_actions: unknown[];
  status: CommandStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  executed_at: string | null;
  created_at: string;
}

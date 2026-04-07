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
}

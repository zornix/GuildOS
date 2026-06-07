import type { Member, Event, AttendanceRecord, Excuse, Fine, CheckinLink } from "../lib/types";

export interface MockDB {
  session: unknown;
  user: Member | null;
  members: Member[];
  events: Event[];
  attendance: AttendanceRecord[];
  excuses: Excuse[];
  fines: Fine[];
  checkin_links: CheckinLink[];
}

export const MOCK_DB: MockDB = {
  session: null,
  user: null,
  members: [
    { id: "u1", name: "Alex Johnson", role: "officer", email: "alex@tke.org", chapter_id: "ch1", status: "active" },
    { id: "u2", name: "Marcus Lee", role: "member", email: "marcus@tke.org", chapter_id: "ch1", status: "active" },
    { id: "u3", name: "Jake Rivera", role: "member", email: "jake@tke.org", chapter_id: "ch1", status: "active" },
    { id: "u4", name: "Tyler Smith", role: "member", email: "tyler@tke.org", chapter_id: "ch1", status: "active" },
    { id: "u5", name: "Chris Nguyen", role: "member", email: "chris@tke.org", chapter_id: "ch1", status: "active" },
    { id: "u6", name: "Devon Park", role: "officer", email: "devon@tke.org", chapter_id: "ch1", status: "active" },
  ],
  events: [
    { id: "e1", title: "Chapter Meeting", date: "2026-04-06", time: "19:00", location: "Chapter House", required: true, fine_amount: 25, chapter_id: "ch1", created_by: "u1" },
    { id: "e2", title: "Philanthropy Event", date: "2026-04-12", time: "10:00", location: "City Park", required: true, fine_amount: 50, chapter_id: "ch1", created_by: "u1" },
    { id: "e3", title: "Study Hours", date: "2026-04-15", time: "18:00", location: "Library 204", required: false, fine_amount: 0, chapter_id: "ch1", created_by: "u6" },
    { id: "e4", title: "Brotherhood Dinner", date: "2026-03-28", time: "18:30", location: "Chapter House", required: true, fine_amount: 25, chapter_id: "ch1", created_by: "u1" },
  ],
  attendance: [
    { event_id: "e4", member_id: "u1", checked_in: true, checked_in_at: "2026-03-28T18:32:00Z", method: "link" },
    { event_id: "e4", member_id: "u2", checked_in: true, checked_in_at: "2026-03-28T18:35:00Z", method: "link" },
    { event_id: "e4", member_id: "u4", checked_in: true, checked_in_at: "2026-03-28T18:40:00Z", method: "link" },
    { event_id: "e4", member_id: "u6", checked_in: true, checked_in_at: "2026-03-28T18:31:00Z", method: "link" },
  ],
  excuses: [
    { id: "ex1", event_id: "e4", member_id: "u3", reason: "Family emergency — had to drive home", status: "approved", reviewed_by: "u1", submitted_at: "2026-03-28T10:00:00Z" },
    { id: "ex2", event_id: "e4", member_id: "u5", reason: "Had a midterm exam conflict", status: "pending", reviewed_by: null, submitted_at: "2026-03-28T16:00:00Z" },
  ],
  fines: [
    { id: "f1", event_id: "e4", member_id: "u5", chapter_id: "ch1", amount: 25, reason: "Missed Brotherhood Dinner (unexcused)", status: "unpaid", issued_at: "2026-03-29T00:00:00Z", paid_at: null, waived_by: null },
  ],
  checkin_links: [],
};

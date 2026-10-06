export type MemberRole = 
  | 'President' 
  | 'Vice President' 
  | 'Treasurer' 
  | 'Secretary' 
  | 'Risk Manager' 
  | 'Recruitment Chair' 
  | 'Social Chair' 
  | 'Philanthropy Chair' 
  | 'Scholarship Chair' 
  | 'Officer' // backend members.role === 'officer' (no specific title exposed)
  | 'Active Member'
  | 'Pledge'
  | 'Pledge Educator'
  | 'Alumni';

export type MemberStanding = 
  | 'Good Standing' 
  | 'Academic Probation' 
  | 'Financial Probation' 
  | 'Social Probation' 
  | 'Social Suspension'
  | 'Financial Hold'
  | 'Suspended';

export interface Member {
  id: string;
  name: string;
  email: string;
  phone: string;
  role: MemberRole;
  status: 'Active' | 'Pledge' | 'Alumni' | 'Inactive';
  standing: MemberStanding;
  major?: string;
  gpa: number;
  // ponytail: field name kept while every UI label says "Unpaid fines" (D12);
  // renaming it is churn across seven files. Rename when it earns its keep.
  duesBalanceCents: number; // Integer cents end to end
  duesBalance: number; // in dollars for display convenience
  attendanceRate: number;
  pledgeClass: string; // e.g. "Fall '22"
  roomNumber?: string;
  securityHoursServed?: number;
  /** Approved security jobs already held (D17) — picker decoration only. */
  priorSecurityShifts?: number;
  /** May we text them? (#57) Absent or false until they opt in; never assumed. */
  smsConsent?: boolean;
}

export type EventType = 
  | 'Chapter Meeting' 
  | 'Philanthropy' 
  | 'Brotherhood' 
  | 'Social' 
  | 'Recruitment' 
  | 'Pledge Education' 
  | 'Community Service';

export type JobStatus = 'To Do' | 'In Progress' | 'Done Reported' | 'Approved' | 'Rejected';

export interface EventJob {
  id: string;
  title: string;
  description: string;
  peopleNeeded: number;
  claimants: { memberId: string; memberName: string; claimedAt: string }[];
  status: JobStatus;
  reportedBy?: string;
  reportedAt?: string;
  approvedBy?: string;
  approvedAt?: string;
  rejectionReason?: string;
  isSecurity?: boolean;
}

export interface SecurityAssignment {
  id: string;
  memberId: string;
  memberName: string;
  station: string;
  assignedBy?: string;
  status?: 'Confirmed' | 'Pending' | 'Completed';
  swapRequestedWithId?: string;
  swapRequestedWithName?: string;
  swapStatus?: 'None' | 'Pending' | 'Accepted' | 'Declined';
}

export interface ChapterEvent {
  id: string;
  title: string;
  description?: string;
  date: string; // YYYY-MM-DD
  startTime: string;
  endTime: string;
  time: string; // display string
  location: string;
  type: EventType;
  audience: 'All Members' | 'Officers Only' | 'Actives Only' | 'Pledges Only';
  required: boolean;
  attendanceTaken: boolean;
  checkedInCount?: number;
  supervisors: string[]; // member names (loaded with the event detail)
  organizers: string[]; // member names (loaded with the event detail)
  /** Backend count from the events list — names only arrive with the detail. */
  organizerCount?: number;
  jobs: EventJob[];
  jobCount?: number;
  openJobCount?: number;
  securityAssignments?: SecurityAssignment[];
  notifiedAt?: string; // last notify blast (backend last_notified_at)
  checkInLinkActive?: boolean;
  checkInToken?: string; // live door code (backend check-in link short_code)
}

export interface Initiative {
  id: string;
  title: string;
  description: string;
  leadChairs: string[]; // member names (never empty)
  category: 'Philanthropy' | 'Social' | 'Housing' | 'Scholarship' | 'Alumni Relations' | 'Rush';
  startDate: string;
  targetDate: string;
  status: 'Active' | 'Completed' | 'Archived';
  jobs: EventJob[];
}

export interface AttendanceRecord {
  id: string;
  eventId: string;
  memberId: string;
  status: 'Present' | 'Absent' | 'Excused' | 'Late';
  markedAt?: string;
  method?: 'Door code' | 'Officer Roll' | 'PIN Check-in';
}

export interface Fine {
  id: string;
  memberId: string;
  memberName: string;
  amountCents: number;
  /** Still owed after payments — what "Mark paid" sends. */
  remainingCents: number;
  amount: number;
  reason: string;
  date: string;
  status: 'Unpaid' | 'Paid';
  issuedBy?: string;
  relatedEventId?: string;
}

export interface Payment {
  id: string;
  memberId: string;
  memberName: string;
  amountCents: number;
  amount: number;
  date: string;
  /** Display label from PAYMENT_METHODS, or "—" when the server does not say. */
  paymentMethod: string;
  reference?: string;
}

export interface Excuse {
  id: string;
  memberId: string;
  memberName: string;
  eventId: string;
  eventName: string;
  eventTitle?: string;
  eventDate: string;
  reason: string;
  documentationUrl?: string;
  status: 'Pending' | 'Approved' | 'Rejected';
  submittedAt: string;
  officerNotes?: string;
  decidedBy?: string;
}

export interface Task {
  id: string;
  title: string;
  description: string;
  assignedTo: string; // Claimant names, falling back to the assigned member
  assignedToId?: string;
  /** Absent only on local demo/draft tasks; API rows always carry these. */
  claimants?: EventJob['claimants'];
  peopleNeeded?: number;
  claimedCount?: number;
  dueDate: string;
  priority: 'Low' | 'Medium' | 'High' | 'Urgent';
  status: 'To Do' | 'In Progress' | 'Completed' | 'Pending' | 'Done Reported' | 'Approved' | 'Cancelled' | 'Unknown';
  /** Which event or initiative the job belongs to; absent for a standalone job. */
  parent?: { kind: 'event' | 'initiative'; title: string };
  category?: 'House Chore' | 'Officer Project' | 'Maintenance' | 'Ritual Prep';
}

export interface PNM {
  id: string;
  name: string;
  hometown: string;
  highSchoolGPA?: number;
  gpa?: number;
  major: string;
  phone: string;
  email?: string;
  year?: string;
  status: 'Lead' | 'Contacted' | 'Invited to House' | 'Bid Extended' | 'Bid Accepted' | 'Declined' | 'Prospect' | 'Rush Active';
  rating?: number; // 1-5 stars
  recommendedBy?: string; // active member name
  comments?: string[];
  notes?: string;
  tags?: string[];
  votesFor?: number;
  votesAgainst?: number;
  eventsAttended?: number;
}

export interface ChapterRule {
  id: string;
  category: 'Conduct' | 'Academics' | 'Finances' | 'Housing' | 'Attendance' | 'Bylaws & Governance' | 'Attendance & Fines' | 'Risk Management & Safety' | 'Academic Standing';
  title: string;
  description: string;
  content?: string;
  fineAmount?: number;
  updatedAt: string;
  clauseNumber?: string;
}

export interface Announcement {
  id: string;
  title: string;
  content: string;
  author: string;
  date: string;
  priority: 'Normal' | 'Urgent' | 'Mandatory';
  channels: ('Calendar' | 'SMS' | 'Push')[];
  calendarDate?: string; // YYYY-MM-DD — the day it occupies on the calendar
  calendarTime?: string; // HH:MM, only ever set alongside calendarDate
}

/** One row of the chapter's message outbox (GET /api/announcements/outbox). */
export interface OutboxMessage {
  id: string;
  eventType: string;
  /** How it goes out. Only officer-sent announcements are 'sms'; the rest is email. */
  channel: OutboxChannel;
  recipientName: string;
  /** Masked to the last four digits by the backend; '' when the member has no phone. */
  recipientPhone: string;
  body: string;
  status: OutboxStatus;
  attempts: number;
  createdAt: string;
  deliveredAt?: string;
  error?: string;
}

export type OutboxChannel = 'email' | 'sms';

export type OutboxStatus = 'pending' | 'sending' | 'sent' | 'failed' | 'simulated';

export interface OutboxNotification {
  id: string;
  timestamp?: string;
  createdAt?: string;
  type: 'EVENT_NOTIFY' | 'ANNOUNCEMENT_BLAST' | 'SECURITY_SWAP' | 'SECURITY_SWAP_REQUEST' | 'SECURITY_ASSIGNED' | 'JOB_REJECTED' | 'FINE_ISSUED' | 'FINE_NOTICE' | 'EXCUSE_DECISION' | 'BID_INVITATION';
  recipient: string;
  recipientPhone?: string;
  message: string;
  status: 'Delivered' | 'Queued' | 'Sent' | 'Failed';
  channel: 'SMS' | 'Push' | 'Email';
}

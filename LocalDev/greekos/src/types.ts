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
  duesBalanceCents: number; // Integer cents end to end
  duesBalance: number; // in dollars for display convenience
  attendanceRate: number;
  pledgeClass: string; // e.g. "Fall '22"
  roomNumber?: string;
  securityHoursServed?: number;
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
  points: number;
  required: boolean;
  attendanceTaken: boolean;
  checkedInCount?: number;
  supervisors: string[]; // member names / IDs (Officers)
  organizers: string[]; // member names / IDs (Chairs/members)
  jobs: EventJob[];
  securityAssignments?: SecurityAssignment[];
  notifiedAt?: string; // set when notify gate passes and blast is sent
  checkInLinkActive?: boolean;
  checkInToken?: string;
  checkInPin?: string;
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
  method?: 'Door Link' | 'Officer Roll' | 'PIN Check-in';
}

export interface Fine {
  id: string;
  memberId: string;
  memberName: string;
  amountCents: number;
  amount: number;
  reason: string;
  date: string;
  status: 'Unpaid' | 'Paid';
  issuedBy?: string;
  relatedEventId?: string;
  ledgerRefId?: string;
}

export interface Payment {
  id: string;
  memberId: string;
  memberName: string;
  amountCents: number;
  amount: number;
  type: 'Dues' | 'Fine' | 'Merch' | 'Assessment' | 'Adjustment';
  date: string;
  paymentMethod: 'Card' | 'Venmo' | 'Bank Transfer' | 'Cash' | 'Ledger Credit';
  reference?: string;
  ledgerRefId?: string;
}

export interface LedgerEntry {
  id: string;
  sequence: number;
  timestamp: string;
  memberId: string;
  memberName: string;
  type: 'DUES_CHARGE' | 'FINE_CHARGE' | 'PAYMENT_CREDIT' | 'ADJUSTMENT_CORRECTION' | 'MERCH_CHARGE';
  amountCents: number;
  balanceAfterCents: number;
  description: string;
  authorizedBy: string;
  correctsEntryId?: string; // If this is an immutable correction referencing an earlier entry
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
  assignedTo: string; // Member name
  assignedToId?: string;
  dueDate: string;
  priority: 'Low' | 'Medium' | 'High' | 'Urgent';
  status: 'To Do' | 'In Progress' | 'Completed' | 'Pending';
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

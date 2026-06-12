export type TreasurySubmissionStatus = "pending" | "approved" | "verified" | "rejected" | "needs_review";

export type TreasuryInvoiceStatus = "draft" | "sent" | "overdue" | "paid" | "unpaid" | "partially_paid" | "cancelled";

export type TreasuryExpenseStatus = "scheduled" | "cleared" | "flagged" | "active" | "invalidated";

export type TreasuryReportDataset = "payments" | "invoices" | "expenses" | "member_balances" | "ledger";

export interface TreasuryStat {
  label: string;
  valueCents?: number;
  value?: string;
  trend: string;
  tone: "mint" | "lavender" | "plum" | "navy";
}

export interface PaymentSubmission {
  id: string;
  memberName: string;
  memo: string;
  amountCents: number;
  status: TreasurySubmissionStatus;
  submittedAt: string;
}

export interface TreasuryInvoice {
  id: string;
  title: string;
  memberName: string;
  amountCents: number;
  dueDate: string;
  status: TreasuryInvoiceStatus;
}

export interface TreasuryExpense {
  id: string;
  vendor: string;
  category: string;
  amountCents: number;
  status: TreasuryExpenseStatus;
  clearsAt: string;
}

export interface TreasuryPayment {
  id: string;
  memberName: string;
  detail: string;
  amountCents: number;
  verifiedAt: string;
}

export interface MemberStatementSummary {
  id: string;
  memberName: string;
  balanceCents: number;
  lastActivity: string;
  standing: "current" | "watch" | "delinquent";
}

export interface TreasuryBalancePoint {
  label: string;
  valueCents: number;
}

export interface TreasuryDashboardMock {
  stats: TreasuryStat[];
  submissions: PaymentSubmission[];
  invoices: TreasuryInvoice[];
  expenses: TreasuryExpense[];
  statements: MemberStatementSummary[];
  balanceTrend: TreasuryBalancePoint[];
}

export interface TreasuryDashboardData {
  stats: TreasuryStat[];
  submissions: PaymentSubmission[];
  pendingSubmissionTotal: number;
  submissionsUnavailableMessage?: string;
  payments: TreasuryPayment[];
  expenses: TreasuryExpense[];
}

export interface TreasuryVerifiedPaymentApiRow {
  id: string;
  chapter_id: string;
  member_id: string;
  invoice_id: string;
  submission_id?: string | null;
  amount_cents: number;
  verified_by?: string | null;
  verified_at?: string | null;
  created_at?: string | null;
}

export interface TreasuryExpenseApiRow {
  id: string;
  chapter_id: string;
  category: string;
  amount_cents: number;
  status: TreasuryExpenseStatus;
  description?: string | null;
  created_by?: string | null;
  created_at?: string | null;
}

export interface TreasuryDashboardApiResponse {
  chapter_balance_cents: number;
  total_outstanding_cents: number;
  pending_proof_count: number;
  overdue_invoice_count: number;
  members_with_balance_count: number;
  recent_payments: TreasuryVerifiedPaymentApiRow[];
  recent_expenses: TreasuryExpenseApiRow[];
}

export interface TreasuryPaymentSubmissionApiRow {
  id: string;
  chapter_id: string;
  member_id: string;
  invoice_id: string;
  claimed_amount_cents: number;
  method: string;
  proof_ref?: string | null;
  status: TreasurySubmissionStatus;
  created_at?: string | null;
  reviewed_at?: string | null;
}

export interface TreasuryPaymentSubmissionsPage {
  data: TreasuryPaymentSubmissionApiRow[];
  next_cursor: string | null;
  total: number;
}

import type {
  PaymentSubmission,
  TreasuryDashboardApiResponse,
  TreasuryDashboardData,
  TreasuryExpense,
  TreasuryExpenseApiRow,
  TreasuryPayment,
  TreasuryPaymentSubmissionApiRow,
  TreasuryPaymentSubmissionsPage,
  TreasuryVerifiedPaymentApiRow,
} from "../contracts/treasury";

function shortId(id: string | null | undefined) {
  return id ? id.slice(0, 8) : "unknown";
}

function titleCase(value: string | null | undefined) {
  if (!value) return "Unknown";
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function pluralize(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function adaptSubmission(row: TreasuryPaymentSubmissionApiRow): PaymentSubmission {
  const proof = row.proof_ref ? `Proof ${row.proof_ref}` : `Invoice ${shortId(row.invoice_id)}`;

  return {
    id: row.id,
    memberName: `Member ${shortId(row.member_id)}`,
    memo: `${titleCase(row.method)} - ${proof}`,
    amountCents: row.claimed_amount_cents,
    status: row.status,
    submittedAt: formatDateTime(row.created_at),
  };
}

function adaptPayment(row: TreasuryVerifiedPaymentApiRow): TreasuryPayment {
  return {
    id: row.id,
    memberName: `Member ${shortId(row.member_id)}`,
    detail: `Invoice ${shortId(row.invoice_id)}`,
    amountCents: row.amount_cents,
    verifiedAt: formatDateTime(row.verified_at ?? row.created_at),
  };
}

function adaptExpense(row: TreasuryExpenseApiRow): TreasuryExpense {
  return {
    id: row.id,
    vendor: row.description || `${titleCase(row.category)} expense`,
    category: titleCase(row.category),
    amountCents: row.amount_cents,
    status: row.status,
    clearsAt: formatDateTime(row.created_at),
  };
}

export function adaptTreasuryDashboard(
  dashboard: TreasuryDashboardApiResponse,
  submissionsPage: TreasuryPaymentSubmissionsPage,
  submissionsUnavailableMessage?: string,
): TreasuryDashboardData {
  const pendingSubmissionTotal = submissionsPage.total;
  const membersWithBalance = dashboard.members_with_balance_count;

  return {
    stats: [
      {
        label: "Operating cash",
        valueCents: dashboard.chapter_balance_cents,
        trend: "Verified payments less active expenses",
        tone: "mint",
      },
      {
        label: "Pending review",
        value: String(dashboard.pending_proof_count),
        trend: pluralize(pendingSubmissionTotal, "proof") + " in queue",
        tone: "lavender",
      },
      {
        label: "Outstanding",
        valueCents: dashboard.total_outstanding_cents,
        trend: pluralize(membersWithBalance, "member") + " with balance",
        tone: "plum",
      },
      {
        label: "Open invoices",
        value: String(dashboard.overdue_invoice_count),
        trend: "Unpaid or partially paid",
        tone: "navy",
      },
    ],
    submissions: submissionsPage.data.map(adaptSubmission),
    pendingSubmissionTotal,
    submissionsUnavailableMessage,
    payments: dashboard.recent_payments.map(adaptPayment),
    expenses: dashboard.recent_expenses.map(adaptExpense),
  };
}

import type { MemberTreasuryDashboardDto } from '../api';
import { formatMoney } from '../formatters';

/** What the member owes right now. This is the number Home and the pay modal
 *  show as "Balance owed". It is NOT the standing-derived unpaid-fines number
 *  on Member.duesBalanceCents. */
export interface MemberBalance {
  memberId: string;
  outstandingCents: number;
  openInvoiceCount: number;
  overdueInvoiceCount: number;
}

export function adaptMemberBalance(dto: MemberTreasuryDashboardDto): MemberBalance {
  const invoices = dto.open_invoices || [];
  return {
    memberId: dto.member_id,
    outstandingCents: dto.balance?.outstanding_balance_cents || 0,
    openInvoiceCount: invoices.length,
    overdueInvoiceCount: invoices.filter(i => i.overdue).length
  };
}

/** A session balance must never be shown for a different member than the one signed in. */
export function balanceForMember(balance: MemberBalance | null, memberId: string | undefined): MemberBalance | null {
  return memberId && balance?.memberId === memberId ? balance : null;
}

/** The one-line status Home shows. Empty string while the balance is unknown
 *  so the banner can render nothing rather than a fake $0. */
export function balanceStatusLine(balance: MemberBalance | null): string {
  if (!balance) return '';
  if (balance.outstandingCents <= 0 && balance.openInvoiceCount === 0) return 'No balance owed';
  const n = balance.openInvoiceCount;
  const invoices = `${n} open invoice${n === 1 ? '' : 's'}`;
  const overdue = balance.overdueInvoiceCount > 0 ? ` (${balance.overdueInvoiceCount} overdue)` : '';
  return `Balance owed ${formatMoney(balance.outstandingCents)} · ${invoices}${overdue}`;
}

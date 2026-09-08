import type { MemberTreasuryDashboardDto } from '../api';

/** What the member owes right now. This is the number Home and the pay modal
 *  show as "Balance owed". It is NOT the standing-derived unpaid-fines number
 *  on Member.duesBalanceCents. */
export interface MemberBalance {
  outstandingCents: number;
  openInvoiceCount: number;
  overdueInvoiceCount: number;
}

export function adaptMemberBalance(dto: MemberTreasuryDashboardDto): MemberBalance {
  const invoices = dto.open_invoices || [];
  return {
    outstandingCents: dto.balance?.outstanding_balance_cents || 0,
    openInvoiceCount: invoices.length,
    overdueInvoiceCount: invoices.filter(i => i.overdue).length
  };
}

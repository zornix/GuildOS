export type FineStatus = "unpaid" | "paid" | "waived";

/** Frontend-facing fine. Money is always integer cents; `formatMoney` is the
 *  only exit to the screen. */
export interface Fine {
  id: string;
  amountCents: number;
  status: FineStatus;
  reason: string;
  issuedAt: string | null;
  memberName: string | null;
  eventTitle: string | null;
  eventDate: string | null;
}

/** A presented fine row from GET /api/fines (an unpaid_invoices fine). */
export interface FineApiRow {
  id: string;
  amount_cents: number;
  status: "unpaid" | "partially_paid" | "paid" | "cancelled";
  reason: string;
  issued_at: string | null;
  member_id: string | null;
  member_name: string | null;
  event_id: string | null;
  event_title: string | null;
  event_date: string | null;
}

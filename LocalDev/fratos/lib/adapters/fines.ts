import type { Fine, FineApiRow, FineStatus } from "../contracts/fines";

function toFineStatus(raw: FineApiRow["status"]): FineStatus {
  switch (raw) {
    case "paid":
      return "paid";
    case "cancelled":
      return "waived"; // a fine is waived by voiding its invoice
    default:
      return "unpaid"; // unpaid | partially_paid — still owed
  }
}

export function adaptFine(row: FineApiRow): Fine {
  return {
    id: row.id,
    amountCents: row.amount_cents,
    status: toFineStatus(row.status),
    reason: row.reason ?? "",
    issuedAt: row.issued_at,
    memberName: row.member_name,
    eventTitle: row.event_title,
    eventDate: row.event_date,
  };
}

export function adaptFines(rows: FineApiRow[]): Fine[] {
  return rows.map(adaptFine);
}

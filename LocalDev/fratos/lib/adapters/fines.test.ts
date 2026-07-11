import { describe, expect, it } from "vitest";
import { adaptFine, adaptFines } from "./fines";
import type { FineApiRow } from "../contracts/fines";

const row = (over: Partial<FineApiRow> = {}): FineApiRow => ({
  id: "f1",
  amount_cents: 2500,
  status: "unpaid",
  reason: "Missed Chapter Meeting (unexcused)",
  issued_at: "2026-07-01T00:00:00Z",
  member_id: "m1",
  member_name: "Jordan",
  event_id: "e1",
  event_title: "Chapter Meeting",
  event_date: "2026-06-30",
  ...over,
});

describe("adaptFine", () => {
  it("carries money as integer cents so no caller guesses the unit", () => {
    expect(adaptFine(row({ amount_cents: 2500 })).amountCents).toBe(2500);
  });

  it("maps invoice statuses onto the three UI states", () => {
    expect(adaptFine(row({ status: "unpaid" })).status).toBe("unpaid");
    expect(adaptFine(row({ status: "partially_paid" })).status).toBe("unpaid");
    expect(adaptFine(row({ status: "paid" })).status).toBe("paid");
    expect(adaptFine(row({ status: "cancelled" })).status).toBe("waived");
  });

  it("renames the drifted DTO fields to the contract", () => {
    const f = adaptFine(row());
    expect(f.reason).toBe("Missed Chapter Meeting (unexcused)");
    expect(f.issuedAt).toBe("2026-07-01T00:00:00Z");
    expect(f.memberName).toBe("Jordan");
    expect(f.eventTitle).toBe("Chapter Meeting");
    expect(f.eventDate).toBe("2026-06-30");
  });

  it("adaptFines maps a whole list", () => {
    expect(adaptFines([row(), row({ id: "f2" })]).map((f) => f.id)).toEqual(["f1", "f2"]);
  });
});

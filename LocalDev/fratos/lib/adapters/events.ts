/** The single place legacy float-dollar event fines cross into integer cents.
 *  `events.fine_amount` is legacy NUMERIC dollars (the events→invoices float
 *  boundary the backend keeps for its import); everything downstream speaks
 *  cents through `formatMoney`. */
export function eventFineAmountCents(event: { fine_amount: number }): number {
  return Math.round(event.fine_amount * 100);
}

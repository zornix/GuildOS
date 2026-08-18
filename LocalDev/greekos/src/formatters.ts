/** Money is integer cents end to end; this is the only place it becomes a string. */
export function formatMoney(cents: number): string {
  return '$' + (cents / 100).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

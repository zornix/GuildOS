/** How members pay, shown on every invoice.
 *
 *  ponytail: a constant, not chapter data — `chapters` has no payment-instructions
 *  column and the pilot is one chapter. Move it to a chapters column (and a
 *  treasurer-facing edit form) the day a second chapter pays differently.
 */
export const PAYMENT_INSTRUCTIONS = [
  'Venmo @TKE-Treasury — put your name and what the payment is for in the note.',
  'Zelle to treasurer@tke.org.',
  'Cash or check: hand it to the treasurer at chapter.',
  'Then submit proof below so the treasury board can verify it.'
];

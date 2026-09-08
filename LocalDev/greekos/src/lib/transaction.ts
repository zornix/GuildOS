import { formatMoney } from '../formatters';

/** The four things a treasurer records. Same words as the backend ledger. */
export type TransactionKind = 'Payment' | 'Fine' | 'Invoice' | 'Adjustment';

export interface TransactionDraft {
  kind: TransactionKind;
  memberId: string;
  memberName: string;
  /** Raw input text. Dollars live here and nowhere else. */
  amountDollars: string;
  memo: string;
}

export interface TransactionPreview {
  valid: boolean;
  error?: string;
  /** Absolute cents, what the ledger row shows. */
  amountCents: number;
  /** Signed effect on the balance owed. */
  deltaCents: number;
  balanceBeforeCents: number;
  balanceAfterCents: number;
  sentence: string;
}

/** "$1,250.50" → 125050. Null for anything that is not money with ≤2 decimals.
 *  String math, so 0.1 stays 10 and never 9.999. */
export function dollarsToCents(input: string): number | null {
  const m = input.trim().replace(/[$,\s]/g, '').match(/^(-?)(\d+)(?:\.(\d{1,2}))?$/);
  if (!m) return null;
  const [, sign, whole, frac = ''] = m;
  const cents = Number(whole) * 100 + Number(frac.padEnd(2, '0'));
  return sign ? -cents : cents;
}

const signed = (cents: number) => `${cents < 0 ? '-' : '+'}${formatMoney(Math.abs(cents))}`;

export function previewTransaction(draft: TransactionDraft, balanceBeforeCents: number): TransactionPreview {
  const fail = (error: string): TransactionPreview => ({
    valid: false, error, amountCents: 0, deltaCents: 0, balanceBeforeCents, balanceAfterCents: balanceBeforeCents, sentence: ''
  });
  if (!draft.memberId) return fail('Pick a member');
  const cents = dollarsToCents(draft.amountDollars);
  if (cents === null) return fail('Enter a dollar amount like 25 or 12.50');

  const name = draft.memberName;
  let deltaCents: number;
  let sentenceHead: string;
  switch (draft.kind) {
    case 'Payment':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = -cents;
      sentenceHead = `Credit ${formatMoney(cents)} to ${name}`;
      break;
    case 'Fine':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = cents;
      sentenceHead = `Charge ${formatMoney(cents)} fine to ${name}`;
      break;
    case 'Invoice':
      if (cents <= 0) return fail('Amount must be more than $0.00');
      deltaCents = cents;
      sentenceHead = `Invoice ${formatMoney(cents)} to ${name}`;
      break;
    case 'Adjustment':
      if (cents === 0) return fail('Adjustment cannot be $0.00');
      deltaCents = cents;
      sentenceHead = `Adjust ${name} by ${signed(cents)}`;
      break;
  }
  const balanceAfterCents = Math.max(0, balanceBeforeCents + deltaCents);
  return {
    valid: true,
    amountCents: Math.abs(cents),
    deltaCents,
    balanceBeforeCents,
    balanceAfterCents,
    sentence: `${sentenceHead} → new balance ${formatMoney(balanceAfterCents)}`
  };
}

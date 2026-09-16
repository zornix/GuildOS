import React, { useId, useState } from 'react';
import { CalendarDays, Paperclip } from 'lucide-react';
import Modal from '../ui/Modal';
import { formatMoney } from '../../formatters';
import { PAYMENT_INSTRUCTIONS } from '../../config/treasury';
import {
  Invoice,
  InvoiceStatus,
  PAYMENT_METHODS,
  ProofDraft,
  formatDueDate,
  invoiceTitle,
  planProof
} from '../../lib/dues';

const STATUS_TONE: Record<InvoiceStatus, string> = {
  Paid: 'bg-emerald-100 text-emerald-800',
  Overdue: 'bg-red-100 text-red-800',
  'Partly paid': 'bg-amber-100 text-amber-900',
  Open: 'bg-slate-200 text-slate-800',
  Void: 'bg-slate-200 text-slate-800'
};

export function InvoiceStatusBadge({ status }: { status: InvoiceStatus }) {
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded shrink-0 ${STATUS_TONE[status]}`}>
      {status}
    </span>
  );
}

interface InvoiceViewProps {
  invoice: Invoice;
  chapterName: string;
  /** False when an officer is reading someone else's invoice. */
  canSubmitProof: boolean;
  /** Proof already sent on this invoice and still awaiting review. */
  pendingProofCents: number;
  onSubmitProof: (invoice: Invoice, draft: ProofDraft, evidence: File | null) => Promise<void>;
  onClose: () => void;
}

/** One invoice, as the member reads it: who is billing, what for, how much is
 *  left, when it is due, how to pay, and the form that says "I paid". */
export default function InvoiceView({
  invoice,
  chapterName,
  canSubmitProof,
  pendingProofCents,
  onSubmitProof,
  onClose
}: InvoiceViewProps) {
  const ids = { amount: useId(), method: useId(), note: useId(), file: useId() };
  const [draft, setDraft] = useState<ProofDraft>({
    amountDollars: (invoice.remainingCents / 100).toFixed(2),
    method: PAYMENT_METHODS[0].value,
    note: ''
  });
  const [evidence, setEvidence] = useState<File | null>(null);
  const [sending, setSending] = useState(false);

  const plan = planProof(invoice, draft);
  const due = formatDueDate(invoice.dueAt);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!plan.valid || sending) return;
    setSending(true);
    try {
      await onSubmitProof(invoice, draft, evidence);
      onClose();
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal maxWidth="max-w-lg" title="Invoice" onClose={onClose}>
      <div className="space-y-5">
        {/* Who is billing, what for */}
        <div className="space-y-1">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wide">
            {chapterName || 'Your chapter'}
          </div>
          <div className="flex items-start justify-between gap-3">
            <h4 className="font-display font-bold text-lg text-slate-900 min-w-0">
              {invoiceTitle(invoice)}
            </h4>
            <InvoiceStatusBadge status={invoice.status} />
          </div>
          {due && (
            <div className="flex items-center gap-1.5 text-xs text-slate-600">
              <CalendarDays className="w-3.5 h-3.5 shrink-0" />
              Due {due}
            </div>
          )}
        </div>

        {/* The money */}
        <div className="rounded-xl border border-slate-200 divide-y divide-slate-100 text-xs">
          <div className="flex justify-between gap-3 px-3 py-2.5">
            <span className="text-slate-600">Amount</span>
            <span className="font-mono font-bold text-slate-900">{formatMoney(invoice.amountCents)}</span>
          </div>
          <div className="flex justify-between gap-3 px-3 py-2.5">
            <span className="text-slate-600">Paid so far</span>
            <span className="font-mono font-bold text-emerald-700">
              {formatMoney(invoice.paidCents)}
            </span>
          </div>
          {pendingProofCents > 0 && (
            <div className="flex justify-between gap-3 px-3 py-2.5">
              <span className="text-slate-600">Awaiting verification</span>
              <span className="font-mono font-bold text-amber-700">
                {formatMoney(pendingProofCents)}
              </span>
            </div>
          )}
          <div className="flex justify-between gap-3 px-3 py-2.5 bg-slate-50">
            <span className="font-bold text-slate-900">Still owed</span>
            <span
              className={`font-mono font-black text-sm ${
                invoice.remainingCents > 0 ? 'text-red-700' : 'text-emerald-700'
              }`}
            >
              {formatMoney(invoice.remainingCents)}
            </span>
          </div>
        </div>

        {/* How to pay */}
        <div>
          <h5 className="text-xs font-bold text-slate-900 mb-1.5">How to pay</h5>
          <ul className="text-xs text-slate-700 space-y-1 list-disc pl-4">
            {PAYMENT_INSTRUCTIONS.map(line => <li key={line}>{line}</li>)}
          </ul>
        </div>

        {/* Submit proof */}
        {canSubmitProof && invoice.remainingCents > 0 && (
          <form onSubmit={submit} className="space-y-3 border-t border-slate-200 pt-4">
            <h5 className="text-xs font-bold text-slate-900">Submit proof</h5>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label htmlFor={ids.amount} className="text-xs font-semibold text-slate-700 block mb-1">
                  Amount paid ($)
                </label>
                <input
                  id={ids.amount}
                  inputMode="decimal"
                  value={draft.amountDollars}
                  onChange={e => setDraft(d => ({ ...d, amountDollars: e.target.value }))}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 font-mono focus:outline-none focus:border-gold"
                />
              </div>
              <div>
                <label htmlFor={ids.method} className="text-xs font-semibold text-slate-700 block mb-1">
                  How you paid
                </label>
                <select
                  id={ids.method}
                  value={draft.method}
                  onChange={e => setDraft(d => ({ ...d, method: e.target.value }))}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 bg-white focus:outline-none focus:border-gold"
                >
                  {PAYMENT_METHODS.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label htmlFor={ids.note} className="text-xs font-semibold text-slate-700 block mb-1">
                Note (optional)
              </label>
              <input
                id={ids.note}
                value={draft.note}
                onChange={e => setDraft(d => ({ ...d, note: e.target.value }))}
                placeholder="Venmo handle, check number, who you handed cash to…"
                className="w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 focus:outline-none focus:border-gold"
              />
            </div>

            <div>
              <label htmlFor={ids.file} className="text-xs font-semibold text-slate-700 block mb-1">
                Screenshot (optional)
              </label>
              <input
                id={ids.file}
                type="file"
                accept="image/*"
                onChange={e => setEvidence(e.target.files?.[0] || null)}
                className="w-full text-xs border border-slate-200 rounded-lg p-2.5 min-h-11 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-xs file:font-semibold cursor-pointer"
              />
              {evidence && (
                <p className="text-xs text-slate-600 mt-1 flex items-center gap-1.5">
                  <Paperclip className="w-3 h-3 shrink-0" />
                  <span className="truncate">{evidence.name}</span>
                </p>
              )}
            </div>

            {!plan.valid && <p className="text-xs text-red-700">{plan.error}</p>}

            <button
              type="submit"
              disabled={!plan.valid || sending}
              className="w-full bg-gold hover:bg-[#c5a02b] disabled:opacity-50 disabled:cursor-not-allowed text-navy font-bold py-3 min-h-11 rounded-lg text-xs transition-all cursor-pointer"
            >
              {sending ? 'Sending…' : 'Submit proof'}
            </button>
            <p className="text-xs text-slate-500">
              Nothing moves until the treasury board verifies it.
            </p>
          </form>
        )}
      </div>
    </Modal>
  );
}

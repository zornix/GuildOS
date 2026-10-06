import React, { useEffect, useId, useState } from 'react';
import type { Member } from '../../types';
import Modal from '../ui/Modal';
import { formatMoney } from '../../formatters';
import { DuesRunDraft, planDuesRun } from '../../lib/dues';

interface DuesRunModalProps {
  /** Everyone the run can bill — active members only. */
  candidates: Member[];
  onSubmit: (draft: DuesRunDraft, idempotencyKey: string) => Promise<void>;
  onClose: () => void;
}

/** One dues run: a title, an amount, a due date, and everyone active minus
 *  whoever the treasurer excludes. Two steps — fill it in, read the sentence,
 *  confirm — because the confirm bills the whole chapter. */
export default function DuesRunModal({ candidates, onSubmit, onClose }: DuesRunModalProps) {
  const ids = { title: useId(), amount: useId(), due: useId() };
  const [title, setTitle] = useState('');
  const [amountDollars, setAmountDollars] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);
  const [sending, setSending] = useState(false);
  // One key per set of values: a retry of the same run reuses it, so the server
  // dedupes the second attempt instead of billing the chapter twice; an edit
  // gets a fresh key, so a changed run is never answered with the old result.
  const [runKey, setRunKey] = useState(() => crypto.randomUUID());
  // The roster can change under an open modal (a refetch); that is a new run too.
  const candidateIds = candidates.map(m => m.id).sort().join(',');
  useEffect(() => { setRunKey(crypto.randomUUID()); }, [title, amountDollars, dueDate, excluded, candidateIds]);

  const draft: DuesRunDraft = {
    title,
    amountDollars,
    dueDate,
    recipientIds: candidates.filter(m => !excluded.has(m.id)).map(m => m.id)
  };
  const plan = planDuesRun(draft);

  const toggle = (id: string) =>
    setExcluded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!plan.valid || sending) return;
    if (!confirming) { setConfirming(true); return; }
    setSending(true);
    try {
      await onSubmit(draft, runKey);
      onClose();
    } catch {
      // The handler already toasted. Stay open so the treasurer can retry —
      // the same idempotency key means a retry cannot double-bill.
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal maxWidth="max-w-lg" title="New dues run" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor={ids.title} className="text-xs font-semibold text-slate-700 block mb-1">
            What is this for
          </label>
          <input
            id={ids.title}
            value={title}
            onChange={e => setTitle(e.target.value)}
            disabled={confirming}
            placeholder="Fall 2026 dues"
            className="w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 focus:outline-none focus:border-gold"
          />
          <p className="text-xs text-slate-500 mt-1">Members see this on the invoice.</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor={ids.amount} className="text-xs font-semibold text-slate-700 block mb-1">
              Amount each ($)
            </label>
            <input
              id={ids.amount}
              inputMode="decimal"
              value={amountDollars}
              onChange={e => setAmountDollars(e.target.value)}
              disabled={confirming}
              placeholder="250.00"
              className="w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 font-mono focus:outline-none focus:border-gold"
            />
          </div>
          <div>
            <label htmlFor={ids.due} className="text-xs font-semibold text-slate-700 block mb-1">
              Due date
            </label>
            <input
              id={ids.due}
              type="date"
              value={dueDate}
              onChange={e => setDueDate(e.target.value)}
              disabled={confirming}
              className="w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 focus:outline-none focus:border-gold"
            />
          </div>
        </div>

        <fieldset disabled={confirming} className="min-w-0">
          <legend className="text-xs font-semibold text-slate-700 mb-1">
            Recipients ({draft.recipientIds.length} of {candidates.length})
          </legend>
          <p className="text-xs text-slate-500 mb-2">Uncheck anyone this run should skip.</p>
          <div className="max-h-48 overflow-y-auto border border-slate-200 rounded-lg divide-y divide-slate-100">
            {candidates.map(m => (
              <label
                key={m.id}
                className="flex items-center gap-3 px-3 py-2 min-h-11 text-xs cursor-pointer hover:bg-slate-50"
              >
                <input
                  type="checkbox"
                  checked={!excluded.has(m.id)}
                  onChange={() => toggle(m.id)}
                  className="w-4 h-4 shrink-0 accent-[#d4af37]"
                />
                <span className="font-semibold text-slate-900 truncate">{m.name}</span>
                <span className="text-slate-500 truncate ml-auto">{m.pledgeClass}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div
          className={`p-3 rounded-xl border text-xs ${
            plan.valid ? 'bg-amber-50 border-amber-200 text-amber-900' : 'bg-slate-50 border-slate-200 text-slate-800'
          }`}
        >
          {plan.valid ? plan.sentence : plan.error}
        </div>

        <div className="flex flex-col sm:flex-row gap-2">
          {confirming && (
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={sending}
              className="sm:w-32 border border-slate-200 text-slate-700 font-bold py-3 min-h-11 rounded-lg text-xs cursor-pointer hover:bg-slate-50"
            >
              Back
            </button>
          )}
          <button
            type="submit"
            disabled={!plan.valid || sending}
            className="flex-1 bg-gold hover:bg-[#c5a02b] disabled:opacity-50 disabled:cursor-not-allowed text-navy font-bold py-3 min-h-11 rounded-lg text-xs transition-all cursor-pointer"
          >
            {sending
              ? 'Creating…'
              : confirming
              ? `Create ${draft.recipientIds.length} invoices · ${formatMoney(plan.totalCents)}`
              : 'Review run'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

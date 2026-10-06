import React, { useId, useState } from 'react';
import type { ChapterEvent, Member } from '../../types';
import Modal from '../ui/Modal';
import { formatMoney } from '../../formatters';
import { PAYMENT_METHODS, type TransactionAccess } from '../../lib/dues';
import {
  EVENT_FINE_CENTS,
  PaymentMethod,
  TransactionDraft,
  TransactionForm,
  TransactionKind,
  draftFromForm,
  previewTransaction
} from '../../lib/transaction';

const KINDS: { kind: TransactionKind; help: string }[] = [
  { kind: 'Payment', help: 'Money received from the member' },
  { kind: 'Fine', help: 'A missed required event or a rule violation' },
  { kind: 'Invoice', help: 'Dues or another bill' },
  { kind: 'Adjustment', help: 'A signed correction, e.g. -10 to forgive $10' }
];

const MEMO_LABEL: Record<TransactionKind, string> = {
  Payment: 'Reference (optional)', Fine: 'Reason', Invoice: 'Description', Adjustment: 'Reason'
};

interface AddTransactionModalProps {
  title?: string;
  /** One line above the form, e.g. which fine a payment settles. */
  note?: string;
  members: Member[];
  /** Required events that already happened — what an event fine attaches to. */
  events: ChapterEvent[];
  access: TransactionAccess;
  /** Prefilled fields. An `invoiceId` locks the member and the kind. */
  initial?: Partial<TransactionForm>;
  /** Resolves once the server has the row; rejects with the message to show. */
  onSubmit: (draft: TransactionDraft, idempotencyKey: string) => Promise<void>;
  onClose: () => void;
}

/** Fill the form, read the sentence, confirm. One idempotency key per set of
 *  values: regenerated on every edit, reused on a retry of the same values. */
export default function AddTransactionModal({
  title = 'Add transaction', note, members, events, access, initial, onSubmit, onClose
}: AddTransactionModalProps) {
  const ids = { member: useId(), amount: useId(), memo: useId(), method: useId(), event: useId() };
  const [form, setForm] = useState<TransactionForm>(() => {
    const memberId = initial?.memberId ?? members[0]?.id ?? '';
    return {
      kind: access.kinds[0] ?? 'Payment', amountDollars: '', memo: '', method: PAYMENT_METHODS[0].value,
      ...initial,
      memberId,
      memberName: members.find(m => m.id === memberId)?.name ?? ''
    };
  });
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const locked = !!initial?.invoiceId;

  const update = (patch: Partial<TransactionForm>) => {
    setForm(f => ({ ...f, ...patch }));
    setKey(crypto.randomUUID());
  };

  // What the server will actually read: an event fine has a fixed amount, and a
  // session that may only fine on events always has an event selected.
  const eventId = form.kind === 'Fine' ? (form.eventId || (access.freeFormFines ? '' : events[0]?.id || '')) : '';
  const eventFine = !!eventId;
  const shown: TransactionForm = eventFine
    ? { ...form, eventId, amountDollars: (EVENT_FINE_CENTS / 100).toFixed(2) }
    : form;
  const preview = previewTransaction(shown);
  const blocked = shown.kind === 'Fine' && !access.freeFormFines && !eventFine
    ? 'No past required event to fine against'
    : '';
  const ok = preview.valid && !blocked;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ok || saving) return;
    if (!confirming) { setConfirming(true); return; }
    setSaving(true);
    setError('');
    try {
      await onSubmit(draftFromForm(shown), key);
      onClose();
    } catch (err) {
      // Same values, same key: a retry cannot double-record.
      setError((err as Error).message || 'Could not save that. Try again.');
    } finally {
      setSaving(false);
    }
  };

  const field = 'w-full text-sm border border-slate-200 rounded-lg p-2.5 min-h-11 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-gold bg-white disabled:bg-slate-50 read-only:bg-slate-50';
  const label = 'text-xs font-semibold text-slate-700 block mb-1';

  return (
    <Modal maxWidth="max-w-lg" title={title} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {note && <p className="text-xs text-slate-600">{note}</p>}

        <div>
          <label htmlFor={ids.member} className={label}>Member</label>
          <select id={ids.member} value={shown.memberId} disabled={locked || confirming}
            onChange={e => update({ memberId: e.target.value, memberName: members.find(m => m.id === e.target.value)?.name || '' })}
            className={field}>
            {members.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </div>

        <fieldset disabled={locked || confirming}>
          <legend className={label}>Kind</legend>
          <div className="grid grid-cols-2 gap-2">
            {KINDS.filter(k => access.kinds.includes(k.kind)).map(({ kind, help }) => (
              <label key={kind} className={`p-2.5 rounded-lg border text-xs cursor-pointer ${shown.kind === kind ? 'border-gold bg-amber-50' : 'border-slate-200 hover:bg-slate-50'}`}>
                <input type="radio" name="kind" value={kind} checked={shown.kind === kind} onChange={() => update({ kind })} className="mr-1.5" />
                <span className="font-bold text-slate-900">{kind}</span>
                <span className={`block pl-5 ${shown.kind === kind ? 'text-amber-950' : 'text-slate-700'}`}>{help}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {shown.kind === 'Fine' && access.eventFines && (
          <div>
            <label htmlFor={ids.event} className={label}>Event</label>
            <select id={ids.event} value={eventId} disabled={confirming} onChange={e => update({ eventId: e.target.value })} className={field}>
              {access.freeFormFines && <option value="">No event — a free-form fine</option>}
              {events.map(ev => <option key={ev.id} value={ev.id}>{ev.title} · {ev.date}</option>)}
            </select>
            {eventFine && (
              <p className="text-xs text-slate-500 mt-1">
                Flat {formatMoney(EVENT_FINE_CENTS)}, set by the chapter. The server only fines an unexcused absence.
              </p>
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor={ids.amount} className={label}>Amount ($)</label>
            <input id={ids.amount} type="text" inputMode="decimal" value={shown.amountDollars} readOnly={eventFine} disabled={confirming}
              onChange={e => update({ amountDollars: e.target.value })}
              placeholder={shown.kind === 'Adjustment' ? '-10.00' : '25.00'}
              className={`${field} font-mono`} required />
          </div>
          {shown.kind === 'Payment' ? (
            <div>
              <label htmlFor={ids.method} className={label}>Method</label>
              <select id={ids.method} value={shown.method} disabled={confirming}
                onChange={e => update({ method: e.target.value as PaymentMethod })} className={field}>
                {PAYMENT_METHODS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </div>
          ) : !eventFine && (
            <div>
              <label htmlFor={ids.memo} className={label}>{MEMO_LABEL[shown.kind]}</label>
              <input id={ids.memo} type="text" value={shown.memo} disabled={confirming}
                onChange={e => update({ memo: e.target.value })}
                placeholder={shown.kind === 'Fine' ? 'Missed chapter (Bylaw II.C.4)' : shown.kind === 'Invoice' ? 'Fall dues' : 'Fine issued in error'}
                className={field} required />
            </div>
          )}
        </div>

        {shown.kind === 'Payment' && (
          <div>
            <label htmlFor={ids.memo} className={label}>{MEMO_LABEL.Payment}</label>
            <input id={ids.memo} type="text" value={shown.memo} disabled={confirming}
              onChange={e => update({ memo: e.target.value })}
              placeholder="Venmo note, check number…" className={field} />
          </div>
        )}

        <div role="status" className={`p-3 rounded-lg text-xs font-semibold ${ok ? 'bg-navy text-white' : 'bg-red-50 text-red-900 border border-red-200'}`}>
          {ok ? preview.sentence : (blocked || preview.error)}
        </div>
        {error && <p role="alert" className="text-xs font-semibold text-red-700">{error}</p>}

        <div className="flex gap-2">
          {confirming && (
            <button type="button" onClick={() => setConfirming(false)} disabled={saving}
              className="flex-1 min-h-11 border border-slate-200 text-slate-800 font-bold rounded-lg text-xs cursor-pointer hover:bg-slate-50 disabled:opacity-50">
              Back
            </button>
          )}
          <button type="submit" disabled={!ok || saving}
            className={`flex-1 min-h-11 font-bold rounded-lg text-xs cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${confirming ? 'bg-navy text-gold hover:bg-[#16304f]' : 'bg-gold text-navy hover:bg-[#c5a02b]'}`}>
            {saving ? 'Saving…' : confirming ? `Confirm ${shown.kind.toLowerCase()}` : 'Preview'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

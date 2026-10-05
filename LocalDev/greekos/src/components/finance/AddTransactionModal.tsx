import React, { useId, useState } from 'react';
import type { Member } from '../../types';
import Modal from '../ui/Modal';
import { formatMoney } from '../../formatters';
import { TransactionForm, TransactionKind, TransactionPreview, previewTransaction } from '../../lib/transaction';

const KINDS: { kind: TransactionKind; help: string }[] = [
  { kind: 'Payment', help: 'Money received from the member' },
  { kind: 'Fine', help: 'A charge for a rule violation' },
  { kind: 'Invoice', help: 'Dues or another bill' },
  { kind: 'Adjustment', help: 'A signed correction, e.g. -10 to forgive $10' }
];

interface AddTransactionModalProps {
  members: Member[];
  balanceCentsOf: (memberId: string) => number;
  onSubmit: (draft: TransactionForm, preview: TransactionPreview) => void;
  onClose: () => void;
}

/** Two steps: fill the form, read the preview sentence, confirm. */
export default function AddTransactionModal({ members, balanceCentsOf, onSubmit, onClose }: AddTransactionModalProps) {
  const ids = { member: useId(), kind: useId(), amount: useId(), memo: useId() };
  const [draft, setDraft] = useState<TransactionForm>({
    kind: 'Payment', memberId: members[0]?.id || '', memberName: members[0]?.name || '', amountDollars: '', memo: ''
  });
  const [confirming, setConfirming] = useState(false);

  const balanceBefore = balanceCentsOf(draft.memberId);
  const preview = previewTransaction(draft, balanceBefore);

  const pickMember = (memberId: string) => {
    const m = members.find(x => x.id === memberId);
    setDraft(d => ({
      ...d,
      memberId,
      memberName: m?.name || '',
      amountDollars: d.kind === 'Payment' && !d.amountDollars && m ? (balanceCentsOf(memberId) / 100).toFixed(2) : d.amountDollars
    }));
  };

  const pickKind = (kind: TransactionKind) =>
    setDraft(d => ({
      ...d,
      kind,
      amountDollars: kind === 'Payment' && !d.amountDollars ? (balanceBefore / 100).toFixed(2) : d.amountDollars
    }));

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!preview.valid) return;
    if (!confirming) { setConfirming(true); return; }
    onSubmit(draft, preview);
    onClose();
  };

  return (
    <Modal maxWidth="max-w-lg" title="Add transaction" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        <div>
          <label htmlFor={ids.member} className="text-xs font-semibold text-slate-700 block mb-1">Member</label>
          <select id={ids.member} value={draft.memberId} onChange={e => pickMember(e.target.value)} disabled={confirming}
            className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold bg-white">
            {members.map(m => <option key={m.id} value={m.id}>{m.name} · balance {formatMoney(balanceCentsOf(m.id))}</option>)}
          </select>
        </div>

        <fieldset disabled={confirming}>
          <legend className="text-xs font-semibold text-slate-700 mb-1">Kind</legend>
          <div className="grid grid-cols-2 gap-2">
            {KINDS.map(({ kind, help }) => (
              <label key={kind} className={`p-2.5 rounded-lg border text-xs cursor-pointer ${draft.kind === kind ? 'border-gold bg-amber-50' : 'border-slate-200 hover:bg-slate-50'}`}>
                <input type="radio" name="kind" value={kind} checked={draft.kind === kind} onChange={() => pickKind(kind)} className="mr-1.5" />
                <span className="font-bold text-slate-900">{kind}</span>
                <span className={`block pl-5 ${draft.kind === kind ? 'text-amber-950' : 'text-slate-700'}`}>{help}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor={ids.amount} className="text-xs font-semibold text-slate-700 block mb-1">Amount ($)</label>
            <input id={ids.amount} type="text" inputMode="decimal" value={draft.amountDollars} disabled={confirming}
              onChange={e => setDraft(d => ({ ...d, amountDollars: e.target.value }))}
              placeholder={draft.kind === 'Adjustment' ? '-10.00' : '25.00'}
              className="w-full text-sm border border-slate-200 rounded-lg p-2.5 font-mono text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-gold bg-white" required />
          </div>
          <div>
            <label htmlFor={ids.memo} className="text-xs font-semibold text-slate-700 block mb-1">Memo</label>
            <input id={ids.memo} type="text" value={draft.memo} disabled={confirming}
              onChange={e => setDraft(d => ({ ...d, memo: e.target.value }))}
              placeholder={draft.kind === 'Fine' ? 'Missed chapter (Bylaw II.C.4)' : 'Fall dues'}
              className="w-full text-sm border border-slate-200 rounded-lg p-2.5 text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-gold bg-white" />
          </div>
        </div>

        <div role="status" className={`p-3 rounded-lg text-xs font-semibold ${preview.valid ? 'bg-navy text-white' : 'bg-red-50 text-red-900 border border-red-200'}`}>
          {preview.valid ? preview.sentence : preview.error}
        </div>

        <div className="flex gap-2">
          {confirming && (
            <button type="button" onClick={() => setConfirming(false)} className="flex-1 min-h-11 border border-slate-200 text-slate-800 font-bold rounded-lg text-xs cursor-pointer hover:bg-slate-50">
              Back
            </button>
          )}
          <button type="submit" disabled={!preview.valid}
            className={`flex-1 min-h-11 font-bold rounded-lg text-xs cursor-pointer disabled:opacity-50 ${confirming ? 'bg-navy text-gold hover:bg-[#16304f]' : 'bg-gold text-navy hover:bg-[#c5a02b]'}`}>
            {confirming ? `Confirm ${draft.kind.toLowerCase()}` : 'Preview'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

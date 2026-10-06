import { useState } from 'react';
import { Image as ImageIcon, ShieldCheck } from 'lucide-react';
import Card from '../ui/Card';
import Modal from '../ui/Modal';
import { formatMoney } from '../../formatters';
import { ProofSubmission, rejectionReasonValid } from '../../lib/dues';

interface ProofQueueProps {
  submissions: ProofSubmission[];
  loading: boolean;
  onOpenEvidence: (evidenceId: string) => Promise<string>;
  onVerify: (submission: ProofSubmission) => Promise<void>;
  onReject: (submission: ProofSubmission, reason: string) => Promise<void>;
}

/** Everything a member has claimed to pay, waiting on the treasury board.
 *  Verify pays the invoice the member named first, then their oldest unpaid
 *  invoice (D7); rejecting needs a reason the member will read. */
export default function ProofQueue({
  submissions,
  loading,
  onOpenEvidence,
  onVerify,
  onReject
}: ProofQueueProps) {
  const [busyId, setBusyId] = useState('');
  const [rejecting, setRejecting] = useState<ProofSubmission | null>(null);
  const [reason, setReason] = useState('');
  const [evidenceUrl, setEvidenceUrl] = useState('');

  const run = async (id: string, work: () => Promise<void>) => {
    setBusyId(id);
    // The handler already toasted on failure; just clear the spinner.
    try { await work(); } catch { /* reported by the caller */ } finally { setBusyId(''); }
  };

  return (
    <Card className="p-4 sm:p-5 space-y-4">
      <div>
        <h3 className="font-display font-bold text-slate-900 text-base flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-emerald-600" />
          Proof queue
        </h3>
        <p className="text-xs text-slate-500">
          Payments members say they made. Verifying pays the invoice they named first, then their oldest unpaid invoice.
        </p>
      </div>

      {loading && <p className="text-xs text-slate-500">Loading…</p>}
      {!loading && submissions.length === 0 && (
        <p className="text-xs text-slate-500">Nothing waiting. Every submitted payment is reviewed.</p>
      )}

      <div className="divide-y divide-slate-100">
        {submissions.map(s => (
          <div key={s.id} className="py-3.5 flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="min-w-0 space-y-1 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold text-xs text-slate-900">{s.memberName}</span>
                <span className="font-mono font-bold text-sm text-emerald-700">
                  {formatMoney(s.claimedCents)}
                </span>
                <span className="text-xs text-slate-500">{s.method}</span>
              </div>
              {s.note && <p className="text-xs text-slate-600 break-words">{s.note}</p>}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs text-slate-500">{s.submittedAt.substring(0, 10)}</span>
                {s.evidenceIds.map((eid, i) => (
                  <button
                    key={eid}
                    type="button"
                    onClick={() => run(s.id, async () => setEvidenceUrl(await onOpenEvidence(eid)))}
                    className="text-xs font-semibold text-navy underline underline-offset-2 flex items-center gap-1 cursor-pointer hover:text-gold"
                  >
                    <ImageIcon className="w-3 h-3 shrink-0" />
                    Proof {s.evidenceIds.length > 1 ? i + 1 : ''}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-2 shrink-0">
              <button
                type="button"
                disabled={busyId === s.id}
                onClick={() => run(s.id, () => onVerify(s))}
                className="text-xs bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-bold px-3 py-1.5 min-h-11 rounded-lg transition-all cursor-pointer"
              >
                Verify
              </button>
              <button
                type="button"
                disabled={busyId === s.id}
                onClick={() => { setRejecting(s); setReason(''); }}
                className="text-xs border border-slate-200 hover:bg-slate-50 disabled:opacity-50 text-slate-800 font-bold px-3 py-1.5 min-h-11 rounded-lg transition-all cursor-pointer"
              >
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>

      {rejecting && (
        <Modal title="Reject this payment?" onClose={() => setRejecting(null)}>
          <form
            onSubmit={e => {
              e.preventDefault();
              if (!rejectionReasonValid(reason)) return;
              const target = rejecting;
              setRejecting(null);
              void run(target.id, () => onReject(target, reason.trim()));
            }}
            className="space-y-4"
          >
            <p className="text-xs text-slate-600">
              {rejecting.memberName} claimed {formatMoney(rejecting.claimedCents)} by {rejecting.method}.
              They will see the reason.
            </p>
            <textarea
              value={reason}
              onChange={e => setReason(e.target.value)}
              rows={3}
              autoFocus
              placeholder="e.g. No Venmo payment arrived under that name — check the handle and resubmit."
              className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-red-400"
            />
            <button
              type="submit"
              disabled={!rejectionReasonValid(reason)}
              className="w-full bg-red-700 hover:bg-red-800 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold py-3 min-h-11 rounded-lg text-xs transition-all cursor-pointer"
            >
              Reject with this reason
            </button>
          </form>
        </Modal>
      )}

      {evidenceUrl && (
        <Modal maxWidth="max-w-2xl" title="Proof" onClose={() => setEvidenceUrl('')}>
          <img src={evidenceUrl} alt="Payment proof" className="w-full rounded-lg border border-slate-200" />
        </Modal>
      )}
    </Card>
  );
}

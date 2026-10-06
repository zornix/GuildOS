import { useState, type Dispatch, type SetStateAction } from 'react';
import { Fine, LedgerEntry, Member, Payment } from '../types';
import { api, optionalOfficerCall, type MemberTreasuryDashboardDto } from '../api';
import { adaptFines, adaptMembers, adaptPayments } from '../adapters';
import { formatMoney } from '../formatters';
import { adaptMemberBalance } from '../lib/balance';
import {
  DuesRunDraft,
  Invoice,
  ProofDraft,
  ProofSubmission,
  adaptInvoices,
  adaptSubmissions,
  duesRunErrorMessage,
  planDuesRun,
  planProof,
  toBase64
} from '../lib/dues';
import { TransactionDraft, submitTransaction as runTransaction } from '../lib/transaction';
import { ShowToast } from './useToast';
import { EnqueueOutbox } from './useOutbox';
import { SyncApi } from './useBackend';

interface Deps {
  members: Member[];
  setMembers: Dispatch<SetStateAction<Member[]>>;
  currentMemberId: string;
  currentMemberName: string;
  isOfficer: boolean;
  backendDown: boolean;
  syncApi: SyncApi;
  showToast: ShowToast;
  enqueueOutbox: EnqueueOutbox;
}

/** Fines, payments, invoices and the officer-recorded transactions. Every
 *  write goes to the server and every number shown afterwards is re-read. */
export function useFinance({ members, setMembers, currentMemberId, backendDown, showToast }: Deps) {
  const [fines, setFines] = useState<Fine[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  // No chapter-wide ledger read exists; nothing renders this. Kept only because
  // useAppData still clears it on load — drop both together.
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  // The signed-in member's real treasury record — the one read behind both the
  // balance banner and the invoice list.
  const [myTreasury, setMyTreasury] = useState<MemberTreasuryDashboardDto | null>(null);
  const [submissions, setSubmissions] = useState<ProofSubmission[]>([]);
  const [queueLoading, setQueueLoading] = useState(false);

  const myBalance = myTreasury ? adaptMemberBalance(myTreasury) : null;
  const myInvoices = adaptInvoices(myTreasury?.open_invoices);

  /** Cents already submitted against each invoice and still awaiting review. */
  const pendingProofCentsOf = (invoiceId: string) =>
    (myTreasury?.pending_submissions || [])
      .filter(s => s.invoice_id === invoiceId)
      .reduce((sum, s) => sum + s.claimed_amount_cents, 0);

  const refreshMyTreasury = async () => {
    if (!currentMemberId) return;
    setMyTreasury(await api.getMemberTreasuryDashboard(currentMemberId));
  };

  const refreshQueue = async () => {
    setQueueLoading(true);
    try {
      const page = await api.listPaymentSubmissions('pending');
      setSubmissions(adaptSubmissions(page.data, new Map(members.map(m => [m.id, m.name]))));
    } finally {
      setQueueLoading(false);
    }
  };

  /** One dues run = one bulk batch of invoices, all with the same due date. */
  const handleCreateDuesRun = async (draft: DuesRunDraft, idempotencyKey: string) => {
    const plan = planDuesRun(draft);
    if (!plan.valid) { showToast(plan.error as string); return; }
    let result;
    try {
      result = await api.bulkCreateInvoices(plan.items, idempotencyKey);
    } catch (err) {
      console.error('Dues run failed', err);
      showToast(duesRunErrorMessage(err));
      throw err;
    }
    await refreshMyTreasury();
    showToast(`Created ${result.count} invoice${result.count === 1 ? '' : 's'} · ${formatMoney(plan.totalCents)} billed.`);
  };

  /** A member's claim that they paid. Evidence is a second call because the
   *  submission has to exist before anything can hang off it. */
  const handleSubmitProof = async (invoice: Invoice, draft: ProofDraft, evidence: File | null) => {
    const plan = planProof(invoice, draft);
    if (!plan.valid) { showToast(plan.error as string); return; }

    let submission;
    try {
      submission = await api.submitPaymentProof(plan.body);
    } catch (err) {
      console.error('Payment proof submission failed', err);
      showToast('Could not submit your payment. Try again.');
      throw err;
    }
    if (evidence) {
      try {
        const bytes = new Uint8Array(await evidence.arrayBuffer());
        await api.addPaymentEvidence(submission.id, evidence.type || 'image/png', toBase64(bytes));
      } catch (err) {
        // The claim is already filed; a failed screenshot must not look like a
        // failed payment submission.
        console.error('Evidence upload failed', err);
        showToast('Payment submitted, but the screenshot did not upload.');
        await refreshMyTreasury();
        return;
      }
    }
    await refreshMyTreasury();
    showToast('Payment submitted. The treasury board will verify it.');
  };

  /** Best-effort refresh after a failed review, so a row someone else already
   *  handled disappears instead of inviting another doomed click. */
  const refreshQueueQuietly = async () => {
    try { await refreshQueue(); } catch (err) { console.error('Queue refresh failed', err); }
  };

  const handleVerifyProof = async (submission: ProofSubmission) => {
    try {
      await api.verifyPaymentSubmission(submission.id);
    } catch (err) {
      console.error('Payment verify failed', err);
      showToast('Could not verify that payment. Refresh and try again.');
      await refreshQueueQuietly();
      throw err;
    }
    await Promise.all([refreshQueue(), refreshMyTreasury()]);
    showToast(`Verified ${formatMoney(submission.claimedCents)} from ${submission.memberName}.`);
  };

  const handleRejectProof = async (submission: ProofSubmission, reason: string) => {
    try {
      await api.rejectPaymentSubmission(submission.id, reason);
    } catch (err) {
      console.error('Payment reject failed', err);
      showToast('Could not reject that payment. Refresh and try again.');
      await refreshQueueQuietly();
      throw err;
    }
    await refreshQueue();
    showToast(`Rejected ${submission.memberName}'s payment.`);
  };

  /** Evidence bytes as a data: URL the proof modal can render. */
  const openEvidence = async (evidenceId: string) => {
    const evidence = await api.getPaymentEvidence(evidenceId);
    return `data:${evidence.content_type};base64,${evidence.data_base64}`;
  };

  const refetchFines = async () => setFines(adaptFines(await api.getFines(), members));

  /** Recent verified payments ride on the officer dashboard; a member session
   *  simply has none to show. */
  const refetchPayments = async () => {
    const dashboard = await optionalOfficerCall(api.getTreasuryDashboard(), null);
    setPayments(adaptPayments(dashboard?.recent_payments || [], members));
  };

  /** Same read as the initial load: the per-member unpaid-fines figure on the
   *  roster comes from standing, so a fine or a payment changes it. */
  const refetchRoster = async () => {
    const [memberRows, standingRows, scoreRows] = await Promise.all([
      api.getMembers(),
      optionalOfficerCall(api.getStandings(), []),
      optionalOfficerCall(api.getScores(), [])
    ]);
    setMembers(adaptMembers(memberRows, standingRows, scoreRows));
  };

  /** Unpaid fines for one member, from their standing row. */
  const balanceCentsOf = (memberId: string) => members.find(m => m.id === memberId)?.duesBalanceCents ?? 0;

  /** Every number on the tab after a write. The write already landed, so a
   *  failed re-read is logged, never shown as a failed transaction. */
  const refetchAfterWrite = async () => {
    const results = await Promise.allSettled([
      refetchFines(),
      refetchPayments(),
      refreshMyTreasury(),
      refetchRoster(),
      optionalOfficerCall(refreshQueue(), undefined)
    ]);
    for (const r of results) if (r.status === 'rejected') console.error('Refresh after transaction failed', r.reason);
  };

  const submitTransaction = (draft: TransactionDraft, idempotencyKey: string) =>
    runTransaction({ api, members, backendDown, refetch: refetchAfterWrite, showToast }, draft, idempotencyKey);

  /** The command console's "fine NAME $N for REASON" (useAppData) lands here. */
  const handleIssueFine = async (fine: { memberId: string; amountCents?: number; amount?: number; reason: string; relatedEventId?: string }) => {
    try {
      await submitTransaction({
        kind: 'Fine',
        memberId: fine.memberId,
        amountCents: fine.amountCents ?? Math.round((fine.amount || 0) * 100),
        reason: fine.reason,
        ...(fine.relatedEventId ? { eventId: fine.relatedEventId } : {})
      }, crypto.randomUUID());
    } catch (err) {
      console.error('Fine failed', err);
      showToast((err as Error).message);
    }
  };

  return {
    fines,
    setFines,
    payments,
    setPayments,
    ledger,
    setLedger,
    myBalance,
    myInvoices,
    setMyTreasury,
    pendingProofCentsOf,
    submissions,
    queueLoading,
    refreshQueue,
    handleCreateDuesRun,
    handleSubmitProof,
    handleVerifyProof,
    handleRejectProof,
    openEvidence,
    balanceCentsOf,
    submitTransaction,
    handleIssueFine
  };
}

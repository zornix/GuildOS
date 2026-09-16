import { useState, type Dispatch, type SetStateAction } from 'react';
import { Fine, LedgerEntry, Member, Payment } from '../types';
import { api, type MemberTreasuryDashboardDto } from '../api';
import { adaptFines } from '../adapters';
import { formatMoney } from '../formatters';
import { adaptMemberBalance } from '../lib/balance';
import {
  DuesRunDraft,
  Invoice,
  ProofDraft,
  adaptInvoices,
  planDuesRun,
  planProof,
  toBase64
} from '../lib/dues';
import { ShowToast } from './useToast';
import { EnqueueOutbox } from './useOutbox';
import { SyncApi } from './useBackend';

interface Deps {
  members: Member[];
  setMembers: Dispatch<SetStateAction<Member[]>>;
  currentMemberId: string;
  currentMemberName: string;
  isOfficer: boolean;
  syncApi: SyncApi;
  showToast: ShowToast;
  enqueueOutbox: EnqueueOutbox;
}

/** Fines, payments and the chapter ledger. Balances live on the member
 *  rows, so this hook writes into the roster state too. */
export function useFinance({ members, setMembers, currentMemberId, currentMemberName, isOfficer, syncApi, showToast, enqueueOutbox }: Deps) {
  const [fines, setFines] = useState<Fine[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  // The signed-in member's real treasury record — the one read behind both the
  // balance banner and, next, their invoices.
  const [myTreasury, setMyTreasury] = useState<MemberTreasuryDashboardDto | null>(null);

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

  /** One dues run = one bulk batch of invoices, all with the same due date. */
  const handleCreateDuesRun = async (draft: DuesRunDraft) => {
    const plan = planDuesRun(draft);
    if (!plan.valid) { showToast(plan.error as string); return; }
    const result = await api.bulkCreateInvoices(plan.items);
    await refreshMyTreasury();
    showToast(`Created ${result.count} invoice${result.count === 1 ? '' : 's'} · ${formatMoney(plan.totalCents)} billed.`);
  };

  /** A member's claim that they paid. Evidence is a second call because the
   *  submission has to exist before anything can hang off it. */
  const handleSubmitProof = async (invoice: Invoice, draft: ProofDraft, evidence: File | null) => {
    const plan = planProof(invoice, draft);
    if (!plan.valid) { showToast(plan.error as string); return; }

    const submission = await api.submitPaymentProof(plan.body);
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

  const refetchFines = async () => setFines(adaptFines(await api.getFines(), members));

  const balanceCentsOf = (memberId: string) => {
    const targetMem = members.find(m => m.id === memberId);
    return targetMem ? (targetMem.duesBalanceCents || targetMem.duesBalance * 100) : 0;
  };

  const setMemberBalance = (memberId: string, newBalanceCents: number) =>
    setMembers(prev => prev.map(m => {
      if (m.id === memberId) {
        return { ...m, duesBalanceCents: newBalanceCents, duesBalance: newBalanceCents / 100 };
      }
      return m;
    }));

  // Local only: the backend has no officer "record a payment" endpoint — money in
  // arrives as a member balance-submission that an officer then verifies.
  const handleRecordPayment = (paymentData: Omit<Payment, 'id' | 'date'>) => {
    const paymentId = 'p_' + Math.random().toString(36).substring(2, 9);
    const ledgerId = 'led_' + (1000 + ledger.length);
    const amountCents = paymentData.amountCents || Math.round(paymentData.amount * 100);

    const newPayment: Payment = {
      ...paymentData,
      id: paymentId,
      date: new Date().toISOString().substring(0, 10),
      ledgerRefId: ledgerId
    };

    // Balance after, derived from the roster updater's `prev` rather than the
    // `members` closure, so two payments in the same tick compose instead of
    // both subtracting from the same stale balance.
    let newBalanceCents = 0;
    setMembers(prev => prev.map(m => {
      if (m.id !== paymentData.memberId) return m;
      newBalanceCents = Math.max(0, (m.duesBalanceCents || m.duesBalance * 100) - amountCents);
      return { ...m, duesBalanceCents: newBalanceCents, duesBalance: newBalanceCents / 100 };
    }));

    setPayments(prev => [newPayment, ...prev]);
    // Entry is built inside the updater so `balanceAfterCents` is the number the
    // roster updater above produced (React runs that one first — roster state is
    // declared earlier), keeping the ledger and the member row on one balance.
    setLedger(prev => [{
      id: ledgerId,
      sequence: ledger.length + 1,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      memberId: paymentData.memberId,
      memberName: paymentData.memberName,
      type: 'PAYMENT_CREDIT',
      amountCents,
      balanceAfterCents: newBalanceCents,
      description: `Payment received via ${paymentData.paymentMethod} (Ref: ${paymentData.reference || 'DIRECT'})`,
      authorizedBy: `${currentMemberName} (${isOfficer ? 'Officer' : 'Self-Service Gateway'})`
    }, ...prev]);

    showToast(`Recorded ${formatMoney(amountCents)} payment from ${paymentData.memberName}.`);
  };

  const handleIssueFine = (fineData: Omit<Fine, 'id' | 'status' | 'date'>) => {
    const fineId = 'f_' + Math.random().toString(36).substring(2, 9);
    const ledgerId = 'led_' + (1000 + ledger.length);
    const amountCents = fineData.amountCents || Math.round(fineData.amount * 100);

    const newFine: Fine = {
      ...fineData,
      id: fineId,
      date: new Date().toISOString().substring(0, 10),
      status: 'Unpaid',
      ledgerRefId: ledgerId
    };

    const newBalanceCents = balanceCentsOf(fineData.memberId) + amountCents;

    const newLedgerEntry: LedgerEntry = {
      id: ledgerId,
      sequence: ledger.length + 1,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      memberId: fineData.memberId,
      memberName: fineData.memberName,
      type: 'FINE_CHARGE',
      amountCents,
      balanceAfterCents: newBalanceCents,
      description: `Disciplinary Fine Citation: ${fineData.reason}`,
      authorizedBy: `${currentMemberName} (Officer)`
    };

    setFines(prev => [newFine, ...prev]);
    setLedger(prev => [newLedgerEntry, ...prev]);
    setMemberBalance(fineData.memberId, newBalanceCents);

    // The API only issues flat fines to unexcused absentees of a known event
    // (POST /api/fines/issue); a free-form citation has no event to attach to.
    if (fineData.relatedEventId) {
      syncApi(() => api.issueFines(fineData.relatedEventId!, [fineData.memberId]), refetchFines);
    }

    enqueueOutbox({
      type: 'FINE_NOTICE',
      recipient: fineData.memberName,
      message: `[GreekOS Fine Notice] You received a ${formatMoney(amountCents)} citation for: ${fineData.reason}`,
      channel: 'SMS'
    });

    showToast(`Assessed ${formatMoney(amountCents)} fine to ${fineData.memberName}.`);
  };

  // ponytail: client-local invoice for the design lab. The real path is
  // POST /api/treasury/invoices; wire it when the form shape has survived a browser test.
  const handlePostInvoice = (inv: { memberId: string; memberName: string; amountCents: number; description: string }) => {
    const ledgerId = 'led_' + (1000 + ledger.length);
    const newBalanceCents = balanceCentsOf(inv.memberId) + inv.amountCents;
    setLedger(prev => [{
      id: ledgerId,
      sequence: ledger.length + 1,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      memberId: inv.memberId,
      memberName: inv.memberName,
      type: 'DUES_CHARGE',
      amountCents: inv.amountCents,
      balanceAfterCents: newBalanceCents,
      description: inv.description || 'Invoice',
      authorizedBy: `${currentMemberName} (Officer)`
    }, ...prev]);
    setMemberBalance(inv.memberId, newBalanceCents);
    showToast(`Invoiced ${formatMoney(inv.amountCents)} to ${inv.memberName}.`);
  };

  const handleApproveFinePayment = (fineId: string) => {
    setFines(prev => prev.map(f => f.id === fineId ? { ...f, status: 'Paid' } : f));
    showToast(`Cleared fine citation.`);
  };

  const handlePostLedgerCorrection = (corr: { memberId: string; amountCents: number; description: string; correctsEntryId?: string }) => {
    const ledgerId = 'led_' + (1000 + ledger.length);
    const targetMem = members.find(m => m.id === corr.memberId);
    const newBalanceCents = Math.max(0, balanceCentsOf(corr.memberId) + corr.amountCents);

    const entry: LedgerEntry = {
      id: ledgerId,
      sequence: ledger.length + 1,
      timestamp: new Date().toISOString().replace('T', ' ').substring(0, 19),
      memberId: corr.memberId,
      memberName: targetMem ? targetMem.name : 'Unknown',
      type: 'ADJUSTMENT_CORRECTION',
      amountCents: Math.abs(corr.amountCents),
      balanceAfterCents: newBalanceCents,
      description: corr.description,
      authorizedBy: `${currentMemberName} (Adjustment)`,
      correctsEntryId: corr.correctsEntryId
    };

    setLedger(prev => [entry, ...prev]);
    setMemberBalance(corr.memberId, newBalanceCents);

    showToast(`Adjustment recorded.`);
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
    handleCreateDuesRun,
    handleSubmitProof,
    balanceCentsOf,
    handleRecordPayment,
    handleIssueFine,
    handlePostInvoice,
    handleApproveFinePayment,
    handlePostLedgerCorrection
  };
}

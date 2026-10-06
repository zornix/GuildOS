import React, { useEffect, useState } from 'react';
import {
  DollarSign,
  AlertCircle,
  FileText,
  Plus,
  History,
  Search,
  Receipt,
  ShieldCheck
} from 'lucide-react';
import { ChapterEvent, Member, Fine, Payment } from '../types';
import Card from './ui/Card';
import AddTransactionModal from './finance/AddTransactionModal';
import DuesRunModal from './finance/DuesRunModal';
import InvoiceView, { InvoiceStatusBadge } from './finance/InvoiceView';
import ProofQueue from './finance/ProofQueue';
import { formatMoney } from '../formatters';
import { can } from '../lib/session';
import { api } from '../api';
import {
  ADJUSTMENT_CREATE_KEY,
  FINES_ISSUE_KEY,
  INVOICE_CREATE_KEY,
  PAYMENT_VERIFY_KEY,
  DuesRunDraft,
  duesRunCandidates,
  Invoice,
  ProofDraft,
  ProofSubmission,
  formatDueDate,
  invoiceTitle,
  transactionAccess
} from '../lib/dues';
import { TransactionDraft, TransactionForm, finableEvents, eventsNeedingFineEligibility } from '../lib/transaction';

interface FinanceModuleProps {
  members: Member[];
  fines: Fine[];
  payments: Payment[];
  /** Chapter events; a fine can attach to a required one that already happened. */
  events: ChapterEvent[];
  /** The backend's own permission keys — every control gates on one. */
  permissions: Set<string>;
  chapterName: string;
  /** The viewed member; modal and tab state reset when it changes. */
  currentMemberId?: string;
  /** The signed-in member's open invoices, dues and fines alike. */
  myInvoices: Invoice[];
  pendingProofCentsOf: (invoiceId: string) => number;
  submissions: ProofSubmission[];
  queueLoading: boolean;
  onRefreshQueue: () => Promise<void>;
  onCreateDuesRun: (draft: DuesRunDraft, idempotencyKey: string) => Promise<void>;
  onSubmitProof: (invoice: Invoice, draft: ProofDraft, evidence: File | null) => Promise<void>;
  onVerifyProof: (submission: ProofSubmission) => Promise<void>;
  onRejectProof: (submission: ProofSubmission, reason: string) => Promise<void>;
  onOpenEvidence: (evidenceId: string) => Promise<string>;
  /** Unpaid fines per member, from standing (useFinance). */
  balanceCentsOf: (memberId: string) => number;
  /** Every officer-recorded transaction. Resolves after the server has it. */
  onSubmitTransaction: (draft: TransactionDraft, idempotencyKey: string) => Promise<void>;
}

/** What the session may do in Treasury, by the keys the endpoints check (#79).
 *  A treasurer holds these without `standing:view_all`, so the officer view is
 *  theirs too. */
export function treasuryAbilities(permissions: Set<string>) {
  const canCreateDuesRun = can(permissions, INVOICE_CREATE_KEY);
  const canVerifyPayments = can(permissions, PAYMENT_VERIFY_KEY);
  const canIssueFines = can(permissions, FINES_ISSUE_KEY);
  const canPostAdjustment = can(permissions, ADJUSTMENT_CREATE_KEY);
  return {
    canCreateDuesRun,
    canVerifyPayments,
    canIssueFines,
    canPostAdjustment,
    isTreasuryOfficer: canCreateDuesRun || canVerifyPayments || canIssueFines || canPostAdjustment
  };
}

/** The Add-transaction modal, opened plain or prefilled from a row. */
interface TransactionPrompt {
  title: string;
  note?: string;
  initial?: Partial<TransactionForm>;
}

const tabClass = (active: boolean) =>
  `pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
    active ? 'text-navy border-b-2 border-gold font-bold' : 'text-slate-500 hover:text-slate-800'
  }`;

export default function FinanceModule({
  members,
  fines,
  payments,
  events,
  permissions,
  chapterName,
  currentMemberId,
  myInvoices,
  pendingProofCentsOf,
  submissions,
  queueLoading,
  onRefreshQueue,
  onCreateDuesRun,
  onSubmitProof,
  onVerifyProof,
  onRejectProof,
  onOpenEvidence,
  balanceCentsOf,
  onSubmitTransaction
}: FinanceModuleProps) {
  const safeMembers = members || [];
  const safeFines = fines || [];
  const safePayments = payments || [];

  const [activeSubTab, setActiveSubTab] = useState<'invoices' | 'overview' | 'fines' | 'payments' | 'queue'>('invoices');
  const [transaction, setTransaction] = useState<TransactionPrompt | null>(null);
  const [eventFineActive, setEventFineActive] = useState(false);
  const [fineStarts, setFineStarts] = useState<Map<string, string>>(new Map());
  const [showDuesRun, setShowDuesRun] = useState(false);
  const [openInvoice, setOpenInvoice] = useState<Invoice | null>(null);
  const [searchMember, setSearchMember] = useState('');

  const { canCreateDuesRun, canVerifyPayments } = treasuryAbilities(permissions);
  const access = transactionAccess(permissions);

  // Everything seeded from the viewed member resets when that member changes;
  // the component itself stays mounted (F-061).
  useEffect(() => {
    setActiveSubTab('invoices');
    setTransaction(null);
    setShowDuesRun(false);
    setOpenInvoice(null);
    setSearchMember('');
  }, [currentMemberId]);

  // The queue is only read when it is on screen — it is the one list that goes
  // stale while another officer works.
  useEffect(() => {
    if (activeSubTab === 'queue' && canVerifyPayments) void onRefreshQueue();
  }, [activeSubTab, canVerifyPayments]);

  // Only an event fine needs eligibility reads, and only recent starts need
  // the server's precise chapter-timezone interpretation.
  const transactionOpen = transaction !== null;
  useEffect(() => {
    let cancelled = false;
    setFineStarts(new Map());
    if (transactionOpen && eventFineActive && access.eventFines) {
      void Promise.allSettled(eventsNeedingFineEligibility(events || []).map(async e => {
        const eligibility = await api.getFineEligibility(e.id);
        return [e.id, eligibility.event_start] as const;
      })).then(results => {
        if (!cancelled) setFineStarts(new Map(results.flatMap(result =>
          result.status === 'fulfilled' ? [result.value] : []
        )));
      });
    }
    return () => { cancelled = true; };
  }, [transactionOpen, eventFineActive, access.eventFines, events, currentMemberId]);

  const recentPaidCents = safePayments.reduce((acc, p) => acc + p.amountCents, 0);
  const unpaidFines = safeFines.filter(f => f.status === 'Unpaid');
  const unpaidFinesCents = unpaidFines.reduce((acc, f) => acc + f.remainingCents, 0);

  const filteredMembers = safeMembers.filter(m =>
    (m.name || '').toLowerCase().includes(searchMember.toLowerCase()) ||
    (m.role || '').toLowerCase().includes(searchMember.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <DollarSign className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Treasury
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Dues, payments and fines.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {canCreateDuesRun && (
            <button
              type="button"
              onClick={() => setShowDuesRun(true)}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
            >
              <FileText className="w-4 h-4" />
              New dues run
            </button>
          )}

          {access.kinds.length > 0 && (
            <button
              type="button"
              onClick={() => setTransaction({ title: 'Add transaction' })}
              className="border border-slate-200 bg-white hover:bg-slate-50 text-slate-800 font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              Add transaction
            </button>
          )}
        </div>
      </div>

      {/* KPI Cards Ribbon */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Card className="p-4 sm:p-5 space-y-1">
          <span className="text-xs font-bold text-emerald-700">Recent payments</span>
          <div className="text-2xl font-display font-black text-emerald-600">
            {formatMoney(recentPaidCents)}
          </div>
          <span className="text-xs text-emerald-700/80">{safePayments.length} verified recently</span>
        </Card>

        <Card className="p-4 sm:p-5 space-y-1">
          <span className="text-xs font-bold text-red-700">Unpaid fines</span>
          <div className="text-2xl font-display font-black text-red-600">
            {formatMoney(unpaidFinesCents)}
          </div>
          <span className="text-xs text-red-700/80">{unpaidFines.length} unpaid</span>
        </Card>
      </div>

      {/* Tabs Menu */}
      <div className="flex border-b border-slate-200 gap-4 sm:gap-6 text-sm font-semibold overflow-x-auto">
        <button onClick={() => setActiveSubTab('invoices')} className={tabClass(activeSubTab === 'invoices')}>
          <FileText className="w-4 h-4" />
          My invoices ({myInvoices.length})
        </button>

        <button onClick={() => setActiveSubTab('overview')} className={tabClass(activeSubTab === 'overview')}>
          <Receipt className="w-4 h-4" />
          Balances
        </button>

        <button onClick={() => setActiveSubTab('fines')} className={tabClass(activeSubTab === 'fines')}>
          <AlertCircle className="w-4 h-4" />
          Fines ({safeFines.length})
        </button>

        <button onClick={() => setActiveSubTab('payments')} className={tabClass(activeSubTab === 'payments')}>
          <History className="w-4 h-4" />
          Payments ({safePayments.length})
        </button>

        {canVerifyPayments && (
          <button onClick={() => setActiveSubTab('queue')} className={tabClass(activeSubTab === 'queue')}>
            <ShieldCheck className="w-4 h-4" />
            Proof queue{submissions.length ? ` (${submissions.length})` : ''}
          </button>
        )}
      </div>

      {/* SubTab 0: The member's own invoices — dues runs and fines alike */}
      {activeSubTab === 'invoices' && (
        <Card className="p-4 sm:p-5 space-y-4">
          <div>
            <h3 className="font-display font-bold text-slate-900 text-base">My invoices</h3>
            <p className="text-xs text-slate-500">
              Everything the chapter has billed you. Open one to see how to pay and submit proof.
            </p>
          </div>

          {myInvoices.length === 0 ? (
            <p className="text-xs text-slate-500">Nothing outstanding. You are square with the chapter.</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {myInvoices.map(inv => {
                const due = formatDueDate(inv.dueAt);
                const pending = pendingProofCentsOf(inv.id);
                return (
                  <button
                    key={inv.id}
                    type="button"
                    onClick={() => setOpenInvoice(inv)}
                    className="w-full text-left py-3.5 flex flex-col sm:flex-row sm:items-center gap-2 hover:bg-slate-50/60 cursor-pointer min-h-11"
                  >
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-bold text-xs text-slate-900">{invoiceTitle(inv)}</span>
                        <InvoiceStatusBadge status={inv.status} />
                      </div>
                      <p className="text-xs text-slate-500">
                        {due ? `Due ${due}` : 'No due date'}
                        {pending > 0 && ` · ${formatMoney(pending)} awaiting verification`}
                      </p>
                    </div>
                    <div className="text-left sm:text-right shrink-0">
                      <div className={`font-mono font-bold text-sm ${inv.remainingCents > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                        {formatMoney(inv.remainingCents)}
                      </div>
                      <div className="text-xs text-slate-500">of {formatMoney(inv.amountCents)}</div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Card>
      )}

      {/* SubTab 1: Unpaid fines per member, from standing */}
      {activeSubTab === 'overview' && (
        <Card className="p-4 sm:p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Balances</h3>
              <p className="text-xs text-slate-500">What each member owes in fines, from their standing.</p>
            </div>

            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                aria-label="Search members"
                placeholder="Search brother..."
                value={searchMember}
                onChange={e => setSearchMember(e.target.value)}
                className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-gold"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-y border-slate-200 text-slate-600 text-xs">
                <tr>
                  <th className="py-2.5 px-3">Brother</th>
                  <th className="py-2.5 px-3 hidden sm:table-cell">Standing</th>
                  <th className="py-2.5 px-3 hidden sm:table-cell">Class</th>
                  <th className="py-2.5 px-3 text-right">Unpaid fines</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredMembers.map(mem => {
                  const balanceCents = balanceCentsOf(mem.id);
                  return (
                    <tr key={mem.id} className="hover:bg-slate-50/60">
                      <td className="py-3 px-3">
                        <div className="font-bold text-slate-900">{mem.name}</div>
                        <div className="text-xs text-slate-500">{mem.role}</div>
                      </td>
                      <td className="py-3 px-3 hidden sm:table-cell">
                        <span className={`text-xs px-2 py-0.5 rounded font-semibold ${
                          mem.standing === 'Good Standing'
                            ? 'bg-emerald-50 text-emerald-800'
                            : 'bg-red-50 text-red-800'
                        }`}>
                          {mem.standing}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-600 hidden sm:table-cell">{mem.memberClass}</td>
                      <td className="py-3 px-3 text-right">
                        <span className={`font-mono font-bold text-xs ${
                          balanceCents > 0 ? 'text-red-600' : 'text-emerald-600'
                        }`}>
                          {formatMoney(balanceCents)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* SubTab 2: Fines Directory */}
      {activeSubTab === 'fines' && (
        <Card className="p-4 sm:p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Fines</h3>
              <p className="text-xs text-slate-500">Issued for unexcused absences and rule violations.</p>
            </div>
          </div>

          <div className="divide-y divide-slate-100">
            {safeFines.map(f => (
              <div key={f.id} className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-xs text-slate-900">{f.memberName}</span>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                      f.status === 'Paid' ? 'bg-emerald-100 text-emerald-800'
                        : f.status === 'Waived' ? 'bg-slate-100 text-slate-600' : 'bg-red-100 text-red-800'
                    }`}>
                      {f.status}
                    </span>
                    <span className="text-xs text-slate-500">{f.date}</span>
                  </div>
                  <p className="text-xs text-slate-600">{f.reason}</p>
                </div>

                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-sm text-red-600">
                    {formatMoney(f.amountCents)}
                  </span>
                  {f.status === 'Unpaid' && f.remainingCents < f.amountCents && (
                    <span className="text-xs text-slate-500">{formatMoney(f.remainingCents)} left</span>
                  )}

                  {canVerifyPayments && f.status === 'Unpaid' && (
                    <button
                      onClick={() => setTransaction({
                        title: 'Mark fine paid',
                        note: `${f.memberName} owes ${formatMoney(f.remainingCents)} for "${f.reason}".`,
                        initial: { kind: 'Payment', memberId: f.memberId, amountDollars: (f.remainingCents / 100).toFixed(2), invoiceId: f.id }
                      })}
                      className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 min-h-11 sm:min-h-0 rounded-lg transition-all cursor-pointer"
                    >
                      Mark paid
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* SubTab 3: Payment Records */}
      {activeSubTab === 'payments' && (
        <Card className="p-4 sm:p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Payments</h3>
              <p className="text-xs text-slate-500">Recent verified payments.</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-y border-slate-200 text-slate-600 text-xs">
                <tr>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3">Brother</th>
                  <th className="py-2.5 px-3">Method & Reference</th>
                  <th className="py-2.5 px-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {safePayments.map(p => (
                  <tr key={p.id} className="hover:bg-slate-50/60">
                    <td className="py-3 px-3 text-slate-500">{p.date}</td>
                    <td className="py-3 px-3 font-bold font-sans text-slate-900">{p.memberName}</td>
                    <td className="py-3 px-3 text-slate-600">{p.paymentMethod} &bull; {p.reference || 'N/A'}</td>
                    <td className="py-3 px-3 text-right font-bold text-emerald-600">
                      {formatMoney(p.amountCents)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {activeSubTab === 'queue' && canVerifyPayments && (
        <ProofQueue
          submissions={submissions}
          loading={queueLoading}
          onOpenEvidence={onOpenEvidence}
          onVerify={onVerifyProof}
          onReject={onRejectProof}
        />
      )}

      {transaction && (
        <AddTransactionModal
          title={transaction.title}
          note={transaction.note}
          initial={transaction.initial}
          members={safeMembers}
          events={finableEvents(events || [], fineStarts)}
          access={access}
          onEventFineModeChange={setEventFineActive}
          onSubmit={onSubmitTransaction}
          onClose={() => setTransaction(null)}
        />
      )}

      {showDuesRun && (
        <DuesRunModal
          candidates={duesRunCandidates(safeMembers)}
          onSubmit={onCreateDuesRun}
          onClose={() => setShowDuesRun(false)}
        />
      )}

      {openInvoice && (
        <InvoiceView
          invoice={openInvoice}
          chapterName={chapterName}
          canSubmitProof
          pendingProofCents={pendingProofCentsOf(openInvoice.id)}
          onSubmitProof={onSubmitProof}
          onClose={() => setOpenInvoice(null)}
        />
      )}
    </div>
  );
}

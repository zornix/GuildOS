import React, { useEffect, useState } from 'react';
import {
  DollarSign,
  CreditCard,
  AlertCircle,
  FileText,
  Plus,
  History,
  Search,
  Receipt,
  RotateCcw,
  ShieldCheck
} from 'lucide-react';
import { Member, Fine, Payment, LedgerEntry } from '../types';
import Modal from './ui/Modal';
import Card from './ui/Card';
import ConfirmDialog from './ui/ConfirmDialog';
import AddTransactionModal from './finance/AddTransactionModal';
import DuesRunModal from './finance/DuesRunModal';
import InvoiceView, { InvoiceStatusBadge } from './finance/InvoiceView';
import ProofQueue from './finance/ProofQueue';
import { formatMoney } from '../formatters';
import type { MemberBalance } from '../lib/balance';
import { can } from '../lib/session';
import {
  ADJUSTMENT_CREATE_KEY,
  FINES_ISSUE_KEY,
  INVOICE_CREATE_KEY,
  PAYMENT_VERIFY_KEY,
  DuesRunDraft,
  Invoice,
  ProofDraft,
  ProofSubmission,
  formatDueDate,
  invoiceTitle
} from '../lib/dues';
import type { TransactionDraft, TransactionPreview } from '../lib/transaction';

interface FinanceModuleProps {
  members: Member[];
  fines: Fine[];
  payments: Payment[];
  ledger: LedgerEntry[];
  /** The backend's own permission keys — every new control gates on one. */
  permissions: Set<string>;
  chapterName: string;
  currentMemberName: string;
  myBalance: MemberBalance | null;
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
  /** The one balance reader, from useFinance. */
  balanceCentsOf: (memberId: string) => number;
  onRecordPayment: (payment: Omit<Payment, 'id' | 'date'>) => void;
  onIssueFine: (fine: Omit<Fine, 'id' | 'status' | 'date'>) => void;
  onPostInvoice: (inv: { memberId: string; memberName: string; amountCents: number; description: string }) => void;
  onApproveFinePayment: (fineId: string) => void;
  onPostLedgerCorrection: (correction: { memberId: string; amountCents: number; description: string; correctsEntryId?: string }) => void;
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

export default function FinanceModule({
  members,
  fines,
  payments,
  ledger,
  permissions,
  chapterName,
  currentMemberName,
  myBalance,
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
  onRecordPayment,
  onIssueFine,
  onPostInvoice,
  onApproveFinePayment,
  onPostLedgerCorrection
}: FinanceModuleProps) {
  const safeMembers = members || [];
  const safeFines = fines || [];
  const safePayments = payments || [];
  const safeLedger = ledger || [];

  const [activeSubTab, setActiveSubTab] = useState<'invoices' | 'overview' | 'fines' | 'ledger' | 'payments' | 'queue'>('invoices');
  const [showAddTransaction, setShowAddTransaction] = useState(false);
  const [showDuesRun, setShowDuesRun] = useState(false);
  const [openInvoice, setOpenInvoice] = useState<Invoice | null>(null);

  const { canCreateDuesRun, canVerifyPayments, canIssueFines, canPostAdjustment, isTreasuryOfficer } =
    treasuryAbilities(permissions);

  // The queue is only read when it is on screen — it is the one list that goes
  // stale while another officer works.
  useEffect(() => {
    if (activeSubTab === 'queue' && canVerifyPayments) void onRefreshQueue();
  }, [activeSubTab, canVerifyPayments]);

  const [showPayModal, setShowPayModal] = useState(false);
  const [showCorrectionModal, setShowCorrectionModal] = useState<LedgerEntry | null>(null);
  const [pendingMarkPaid, setPendingMarkPaid] = useState<{ member: Member; balanceCents: number } | null>(null);
  const [pendingFinePaid, setPendingFinePaid] = useState<Fine | null>(null);

  // Search & Filter
  const [searchMember, setSearchMember] = useState('');
  const [ledgerFilter, setLedgerFilter] = useState('ALL');

  // Payment Form
  const [payAmount, setPayAmount] = useState('');
  const [payMethod, setPayMethod] = useState<'Card' | 'Venmo' | 'Bank Transfer'>('Venmo');

  // Correction Form
  const [correctionAmountCents, setCorrectionAmountCents] = useState(0);
  const [correctionReason, setCorrectionReason] = useState('');

  // Financial Computations in Integer Cents
  const totalReceivablesCents = safeMembers.reduce((acc, m) => acc + (m.duesBalanceCents || ((m.duesBalance || 0) * 100)), 0);
  const totalPaidCents = safePayments.reduce((acc, p) => acc + (p.amountCents || ((p.amount || 0) * 100)), 0);
  const totalUnpaidFinesCents = safeFines.filter(f => f.status === 'Unpaid').reduce((acc, f) => acc + (f.amountCents || ((f.amount || 0) * 100)), 0);

  const currentMember = safeMembers.find(m => m.name === currentMemberName);

  /** One dispatcher for the four kinds; each lands on an existing handler. */
  const submitTransaction = (draft: TransactionDraft, preview: TransactionPreview) => {
    switch (draft.kind) {
      case 'Payment':
        onRecordPayment({
          memberId: draft.memberId, memberName: draft.memberName,
          amount: preview.amountCents / 100, amountCents: preview.amountCents,
          type: 'Dues', paymentMethod: 'Cash', reference: draft.memo || 'IN_PERSON'
        });
        break;
      case 'Fine':
        onIssueFine({
          memberId: draft.memberId, memberName: draft.memberName,
          amount: preview.amountCents / 100, amountCents: preview.amountCents,
          reason: draft.memo || 'Fine', issuedBy: currentMemberName
        });
        break;
      case 'Invoice':
        onPostInvoice({ memberId: draft.memberId, memberName: draft.memberName, amountCents: preview.amountCents, description: draft.memo });
        break;
      case 'Adjustment':
        onPostLedgerCorrection({ memberId: draft.memberId, amountCents: preview.deltaCents, description: draft.memo || 'Adjustment' });
        break;
    }
  };

  const handlePaySubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentMember) return;
    const amountDollars = parseFloat(payAmount) || 0;
    if (amountDollars <= 0) return;

    onRecordPayment({
      memberId: currentMember.id,
      memberName: currentMember.name,
      amount: amountDollars,
      amountCents: Math.round(amountDollars * 100),
      type: 'Dues',
      paymentMethod: payMethod,
      reference: 'TX_' + Math.random().toString(36).substring(2, 8).toUpperCase()
    });

    setShowPayModal(false);
  };

  const handleCorrectionSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!showCorrectionModal) return;

    onPostLedgerCorrection({
      memberId: showCorrectionModal.memberId,
      amountCents: Number(correctionAmountCents),
      description: `Correction for Entry #${showCorrectionModal.sequence}: ${correctionReason}`,
      correctsEntryId: showCorrectionModal.id
    });

    setShowCorrectionModal(null);
    setCorrectionReason('');
  };

  const filteredMembers = safeMembers.filter(m => 
    (m.name || '').toLowerCase().includes(searchMember.toLowerCase()) || 
    (m.role || '').toLowerCase().includes(searchMember.toLowerCase())
  );

  const filteredLedger = safeLedger.filter(entry => {
    if (ledgerFilter === 'ALL') return true;
    return entry.type === ledgerFilter;
  });

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
            Dues, payments, fines, and the chapter ledger.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {!isTreasuryOfficer && (
            <button
              onClick={() => { setPayAmount(myBalance ? (myBalance.outstandingCents / 100).toFixed(2) : ''); setShowPayModal(true); }}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
            >
              <CreditCard className="w-4 h-4" />
              Pay balance
            </button>
          )}

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

          {canIssueFines && (
            <button
              type="button"
              onClick={() => setShowAddTransaction(true)}
              className="border border-slate-200 bg-white hover:bg-slate-50 text-slate-800 font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              Add transaction
            </button>
          )}
        </div>
      </div>

      {/* KPI Cards Ribbon */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="p-4 sm:p-5 space-y-1">
          <span className="text-xs font-bold text-slate-500">Outstanding</span>
          <div className="text-2xl font-display font-black text-slate-900">
            {formatMoney(totalReceivablesCents)}
          </div>
          <span className="text-xs text-slate-500">Unpaid balances on the roster</span>
        </Card>

        <Card className="p-4 sm:p-5 space-y-1">
          <span className="text-xs font-bold text-emerald-700">Collected</span>
          <div className="text-2xl font-display font-black text-emerald-600">
            {formatMoney(totalPaidCents)}
          </div>
          <span className="text-xs text-emerald-700/80">{payments.length} verified transactions</span>
        </Card>

        <Card className="p-4 sm:p-5 space-y-1">
          <span className="text-xs font-bold text-red-700">Unpaid fines</span>
          <div className="text-2xl font-display font-black text-red-600">
            {formatMoney(totalUnpaidFinesCents)}
          </div>
          <span className="text-xs text-red-700/80">{fines.filter(f => f.status === 'Unpaid').length} unpaid</span>
        </Card>
      </div>

      {/* Tabs Menu */}
      <div className="flex border-b border-slate-200 gap-4 sm:gap-6 text-sm font-semibold overflow-x-auto">
        <button
          onClick={() => setActiveSubTab('invoices')}
          className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'invoices'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <FileText className="w-4 h-4" />
          My invoices ({myInvoices.length})
        </button>

        <button
          onClick={() => setActiveSubTab('overview')}
          className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'overview'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <Receipt className="w-4 h-4" />
          Balances
        </button>

        <button
          onClick={() => setActiveSubTab('ledger')}
          className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'ledger'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          Chapter ledger
        </button>

        <button
          onClick={() => setActiveSubTab('fines')}
          className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'fines'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <AlertCircle className="w-4 h-4" />
          Fines ({fines.length})
        </button>

        <button
          onClick={() => setActiveSubTab('payments')}
          className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'payments'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <History className="w-4 h-4" />
          Payments ({payments.length})
        </button>

        {canVerifyPayments && (
          <button
            onClick={() => setActiveSubTab('queue')}
            className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
              activeSubTab === 'queue'
                ? 'text-navy border-b-2 border-gold font-bold'
                : 'text-slate-500 hover:text-slate-800'
            }`}
          >
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

      {/* SubTab 1: Member Balances */}
      {activeSubTab === 'overview' && (
        <Card className="p-4 sm:p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Balances</h3>
              <p className="text-xs text-slate-500">Starts from unpaid fines; demo transactions adjust it locally.</p>
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
                  <th className="py-2.5 px-3 hidden sm:table-cell">Pledge Class</th>
                  <th className="py-2.5 px-3 text-right">Balance</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredMembers.map(mem => {
                  const balanceCents = balanceCentsOf(mem.id);
                  const isDelinquent = balanceCents > 50000; // >$500

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
                      <td className="py-3 px-3 text-slate-600 hidden sm:table-cell">{mem.pledgeClass}</td>
                      <td className="py-3 px-3 text-right">
                        <span className={`font-mono font-bold text-xs ${
                          balanceCents > 0 ? 'text-red-600' : 'text-emerald-600'
                        }`}>
                          {formatMoney(balanceCents)}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right">
                        {balanceCents > 0 && canVerifyPayments && (
                          <button
                            onClick={() => setPendingMarkPaid({ member: mem, balanceCents })}
                            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-800 font-semibold px-2 py-1 min-h-11 sm:min-h-0 rounded transition-all cursor-pointer"
                          >
                            Mark Paid
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* SubTab 2: Permanent Append-Only Audit Ledger */}
      {activeSubTab === 'ledger' && (
        <Card className="p-4 sm:p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
                Chapter ledger
              </h3>
              <p className="text-xs text-slate-500">
                There is no chapter-wide ledger API yet. Corrections here stay on this session.
              </p>
            </div>

            <div className="flex gap-1 bg-slate-100 p-1 rounded-lg text-xs overflow-x-auto">
              {['ALL', 'DUES_CHARGE', 'FINE_CHARGE', 'PAYMENT_CREDIT', 'ADJUSTMENT_CORRECTION'].map(ft => (
                <button
                  key={ft}
                  onClick={() => setLedgerFilter(ft)}
                  className={`px-2 py-1 min-h-11 sm:min-h-0 shrink-0 whitespace-nowrap rounded font-semibold transition-all cursor-pointer ${
                    ledgerFilter === ft ? 'bg-navy text-gold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {ft === 'ALL' ? 'All Ledger' : ft.replace('_', ' ')}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-y border-slate-200 text-slate-600 text-xs">
                <tr>
                  <th className="py-2.5 px-3">Seq #</th>
                  <th className="py-2.5 px-3">Timestamp</th>
                  <th className="py-2.5 px-3">Brother</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Description & Authorized By</th>
                  <th className="py-2.5 px-3 text-right">Amount</th>
                  <th className="py-2.5 px-3 text-right">Balance After</th>
                  {canPostAdjustment && <th className="py-2.5 px-3 text-right">Correction</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {filteredLedger.map(entry => {
                  const isCredit = entry.type === 'PAYMENT_CREDIT';
                  return (
                    <tr key={entry.id} className="hover:bg-slate-50/60 text-xs">
                      <td className="py-3 px-3 font-bold text-slate-500">#{entry.sequence}</td>
                      <td className="py-3 px-3 text-slate-500 text-xs">{entry.timestamp}</td>
                      <td className="py-3 px-3 font-bold text-slate-900 font-sans">{entry.memberName}</td>
                      <td className="py-3 px-3">
                        <span className={`text-xs px-2 py-0.5 rounded font-bold ${
                          entry.type === 'PAYMENT_CREDIT' 
                            ? 'bg-emerald-100 text-emerald-800' 
                            : entry.type === 'FINE_CHARGE' 
                            ? 'bg-red-100 text-red-800'
                            : entry.type === 'ADJUSTMENT_CORRECTION'
                            ? 'bg-purple-100 text-purple-800'
                            : 'bg-blue-100 text-blue-800'
                        }`}>
                          {entry.type}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-sans">
                        <div className="text-slate-800 font-medium">{entry.description}</div>
                        <div className="text-xs text-slate-500">Auth: {entry.authorizedBy}</div>
                        {entry.correctsEntryId && (
                          <div className="text-xs text-purple-700 mt-0.5">
                            Ref Correction &rarr; {entry.correctsEntryId}
                          </div>
                        )}
                      </td>
                      <td className={`py-3 px-3 text-right font-bold ${isCredit ? 'text-emerald-600' : 'text-red-600'}`}>
                        {isCredit ? '-' : '+'}{formatMoney(entry.amountCents)}
                      </td>
                      <td className="py-3 px-3 text-right text-slate-700">
                        {formatMoney(entry.balanceAfterCents)}
                      </td>
                      {canPostAdjustment && (
                        <td className="py-3 px-3 text-right">
                          <button
                            onClick={() => {
                              setShowCorrectionModal(entry);
                              setCorrectionAmountCents(-entry.amountCents);
                            }}
                            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-2 py-1 min-h-11 sm:min-h-0 rounded transition-all cursor-pointer flex items-center gap-1 ml-auto"
                            title="Add an adjustment row for this entry"
                          >
                            <RotateCcw className="w-3 h-3" />
                            Correct
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* SubTab 3: Fines Directory */}
      {activeSubTab === 'fines' && (
        <Card className="p-4 sm:p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Fines</h3>
              <p className="text-xs text-slate-500">Issued for unexcused absences and rule violations.</p>
            </div>
          </div>

          <div className="divide-y divide-slate-100">
            {fines.map(f => (
              <div key={f.id} className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-xs text-slate-900">{f.memberName}</span>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                      f.status === 'Paid' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'
                    }`}>
                      {f.status}
                    </span>
                    <span className="text-xs text-slate-500">{f.date}</span>
                  </div>
                  <p className="text-xs text-slate-600">{f.reason}</p>
                </div>

                <div className="flex items-center gap-3">
                  <span className="font-mono font-bold text-sm text-red-600">
                    {formatMoney(f.amountCents || f.amount * 100)}
                  </span>

                  {canVerifyPayments && f.status === 'Unpaid' && (
                    <button
                      onClick={() => setPendingFinePaid(f)}
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

      {/* SubTab 4: Payment Records */}
      {activeSubTab === 'payments' && (
        <Card className="p-4 sm:p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Payments</h3>
              <p className="text-xs text-slate-500">Verified payments from the backend, plus demo payments recorded here.</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-y border-slate-200 text-slate-600 text-xs">
                <tr>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3">Brother</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Method & Reference</th>
                  <th className="py-2.5 px-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {payments.map(p => (
                  <tr key={p.id} className="hover:bg-slate-50/60">
                    <td className="py-3 px-3 text-slate-500">{p.date}</td>
                    <td className="py-3 px-3 font-bold font-sans text-slate-900">{p.memberName}</td>
                    <td className="py-3 px-3">{p.type}</td>
                    <td className="py-3 px-3 text-slate-600">{p.paymentMethod} &bull; {p.reference || 'N/A'}</td>
                    <td className="py-3 px-3 text-right font-bold text-emerald-600">
                      {formatMoney(p.amountCents || p.amount * 100)}
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

      {showAddTransaction && (
        <AddTransactionModal
          members={safeMembers}
          balanceCentsOf={balanceCentsOf}
          onSubmit={submitTransaction}
          onClose={() => setShowAddTransaction(false)}
        />
      )}

      {showDuesRun && (
        <DuesRunModal
          candidates={safeMembers.filter(m => m.status === 'Active' || m.status === 'Pledge')}
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

      {/* MODAL: Pay Dues (Member) */}
      {showPayModal && currentMember && (
        <Modal title="Pay balance" onClose={() => setShowPayModal(false)}>

            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs mb-4">
              <div className="text-amber-900 font-bold">Balance owed</div>
              <div className="text-xl font-display font-black text-amber-900">
                {myBalance ? formatMoney(myBalance.outstandingCents) : 'Balance unavailable'}
              </div>
            </div>

            <form onSubmit={handlePaySubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Payment Amount ($)</label>
                <input
                  type="number"
                  value={payAmount}
                  onChange={e => setPayAmount(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Payment Method</label>
                <select
                  value={payMethod}
                  onChange={e => setPayMethod(e.target.value as any)}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                >
                  <option value="Venmo">Venmo</option>
                  <option value="Card">Card</option>
                  <option value="Bank Transfer">Bank transfer</option>
                </select>
              </div>

              <button
                type="submit"
                className="w-full bg-gold hover:bg-[#c5a02b] text-navy font-bold py-3 min-h-11 rounded-lg text-xs transition-all"
              >
                Record payment
              </button>
            </form>
        </Modal>
      )}

      {/* MODAL: Add adjustment */}
      {showCorrectionModal && (
        <Modal title="Add adjustment" onClose={() => setShowCorrectionModal(null)}>

            <p className="text-xs text-slate-600 mb-3">
              Creating linked correction for Sequence #{showCorrectionModal.sequence} ({showCorrectionModal.description}).
            </p>

            <form onSubmit={handleCorrectionSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Adjustment in cents (negative reduces the balance)</label>
                <input
                  type="number"
                  value={correctionAmountCents}
                  onChange={e => setCorrectionAmountCents(Number(e.target.value))}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 font-mono focus:outline-none focus:border-purple-500"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Audit Correction Reason</label>
                <textarea
                  value={correctionReason}
                  onChange={e => setCorrectionReason(e.target.value)}
                  placeholder="e.g. Fine was issued in error; brother had approved excused absence on file."
                  rows={2}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-purple-500"
                  required
                />
              </div>

              <button
                type="submit"
                className="w-full bg-purple-700 hover:bg-purple-800 text-white font-bold py-3 min-h-11 rounded-lg text-xs transition-all"
              >
                Record adjustment
              </button>
            </form>
        </Modal>
      )}

      {pendingMarkPaid && (
        <ConfirmDialog
          title="Mark paid?"
          body={<p>Record a cash payment of <strong>{formatMoney(pendingMarkPaid.balanceCents)}</strong> from <strong>{pendingMarkPaid.member.name}</strong>. Their balance becomes $0.00.</p>}
          confirmLabel="Mark paid"
          onCancel={() => setPendingMarkPaid(null)}
          onConfirm={() => {
            onRecordPayment({
              memberId: pendingMarkPaid.member.id, memberName: pendingMarkPaid.member.name,
              amount: pendingMarkPaid.balanceCents / 100, amountCents: pendingMarkPaid.balanceCents,
              type: 'Dues', paymentMethod: 'Cash', reference: 'IN_PERSON_CASH'
            });
            setPendingMarkPaid(null);
          }}
        />
      )}
      {pendingFinePaid && (
        <ConfirmDialog
          title="Mark fine paid?"
          body={<p><strong>{pendingFinePaid.memberName}</strong>'s {formatMoney(pendingFinePaid.amountCents || pendingFinePaid.amount * 100)} fine for "{pendingFinePaid.reason}" will show as paid.</p>}
          confirmLabel="Mark paid"
          onCancel={() => setPendingFinePaid(null)}
          onConfirm={() => { onApproveFinePayment(pendingFinePaid.id); setPendingFinePaid(null); }}
        />
      )}
    </div>
  );
}

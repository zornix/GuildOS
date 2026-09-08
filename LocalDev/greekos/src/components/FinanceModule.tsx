import React, { useState } from 'react';
import {
  DollarSign,
  CreditCard,
  AlertCircle,
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
import { formatMoney } from '../formatters';

interface FinanceModuleProps {
  members: Member[];
  fines: Fine[];
  payments: Payment[];
  ledger: LedgerEntry[];
  isOfficer: boolean;
  currentMemberName: string;
  onRecordPayment: (payment: Omit<Payment, 'id' | 'date'>) => void;
  onIssueFine: (fine: Omit<Fine, 'id' | 'status' | 'date'>) => void;
  onApproveFinePayment: (fineId: string) => void;
  onPostLedgerCorrection: (correction: { memberId: string; amountCents: number; description: string; correctsEntryId: string }) => void;
}

export default function FinanceModule({
  members,
  fines,
  payments,
  ledger,
  isOfficer,
  currentMemberName,
  onRecordPayment,
  onIssueFine,
  onApproveFinePayment,
  onPostLedgerCorrection
}: FinanceModuleProps) {
  const safeMembers = members || [];
  const safeFines = fines || [];
  const safePayments = payments || [];
  const safeLedger = ledger || [];

  const [activeSubTab, setActiveSubTab] = useState<'overview' | 'fines' | 'ledger' | 'payments'>('overview');
  const [showIssueFineModal, setShowIssueFineModal] = useState(false);
  const [showPayModal, setShowPayModal] = useState(false);
  const [showCorrectionModal, setShowCorrectionModal] = useState<LedgerEntry | null>(null);
  const [pendingMarkPaid, setPendingMarkPaid] = useState<{ member: Member; balanceCents: number } | null>(null);
  const [pendingFinePaid, setPendingFinePaid] = useState<Fine | null>(null);

  // Search & Filter
  const [searchMember, setSearchMember] = useState('');
  const [ledgerFilter, setLedgerFilter] = useState('ALL');

  // Issue Fine Form
  const [selectedMemberId, setSelectedMemberId] = useState(safeMembers[0]?.id || '');
  const [fineAmount, setFineAmount] = useState('25');
  const [fineReason, setFineReason] = useState('');

  // Payment Form
  const [payAmount, setPayAmount] = useState('150');
  const [payMethod, setPayMethod] = useState<'Card' | 'Venmo' | 'Bank Transfer'>('Venmo');

  // Correction Form
  const [correctionAmountCents, setCorrectionAmountCents] = useState(0);
  const [correctionReason, setCorrectionReason] = useState('');

  // Financial Computations in Integer Cents
  const totalReceivablesCents = safeMembers.reduce((acc, m) => acc + (m.duesBalanceCents || ((m.duesBalance || 0) * 100)), 0);
  const totalPaidCents = safePayments.reduce((acc, p) => acc + (p.amountCents || ((p.amount || 0) * 100)), 0);
  const totalUnpaidFinesCents = safeFines.filter(f => f.status === 'Unpaid').reduce((acc, f) => acc + (f.amountCents || ((f.amount || 0) * 100)), 0);

  const currentMember = safeMembers.find(m => m.name === currentMemberName);

  const handleIssueFineSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const mem = safeMembers.find(m => m.id === selectedMemberId);
    if (!mem) return;

    const amountDollars = parseFloat(fineAmount) || 25;
    onIssueFine({
      memberId: mem.id,
      memberName: mem.name,
      amount: amountDollars,
      amountCents: Math.round(amountDollars * 100),
      reason: fineReason,
      issuedBy: currentMemberName
    });

    setFineReason('');
    setShowIssueFineModal(false);
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

        <div className="flex gap-2">
          {!isOfficer && (
            <button
              onClick={() => setShowPayModal(true)}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
            >
              <CreditCard className="w-4 h-4" />
              Pay My Dues / Fines
            </button>
          )}

          {isOfficer && (
            <button
              onClick={() => setShowIssueFineModal(true)}
              className="bg-red-700 hover:bg-red-800 text-white font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              Issue Fine Citation
            </button>
          )}
        </div>
      </div>

      {/* KPI Cards Ribbon */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="p-5 space-y-1">
          <span className="text-xs font-bold text-slate-500">Total Chapter Receivables</span>
          <div className="text-2xl font-display font-black text-slate-900">
            {formatMoney(totalReceivablesCents)}
          </div>
          <span className="text-xs text-slate-500">Outstanding brother dues balances</span>
        </Card>

        <Card className="p-5 space-y-1">
          <span className="text-xs font-bold text-emerald-700">Collected This Semester</span>
          <div className="text-2xl font-display font-black text-emerald-600">
            {formatMoney(totalPaidCents)}
          </div>
          <span className="text-xs text-emerald-700/80">{payments.length} verified transactions</span>
        </Card>

        <Card className="p-5 space-y-1">
          <span className="text-xs font-bold text-red-700">Unpaid Fines Outstanding</span>
          <div className="text-2xl font-display font-black text-red-600">
            {formatMoney(totalUnpaidFinesCents)}
          </div>
          <span className="text-xs text-red-700/80">{fines.filter(f => f.status === 'Unpaid').length} active citations</span>
        </Card>
      </div>

      {/* Tabs Menu */}
      <div className="flex border-b border-slate-200 gap-6 text-sm font-semibold">
        <button
          onClick={() => setActiveSubTab('overview')}
          className={`pb-3 transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'overview'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <Receipt className="w-4 h-4" />
          Member Balances & Dues
        </button>

        <button
          onClick={() => setActiveSubTab('ledger')}
          className={`pb-3 transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'ledger'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <ShieldCheck className="w-4 h-4" />
          Append-Only Audit Ledger
        </button>

        <button
          onClick={() => setActiveSubTab('fines')}
          className={`pb-3 transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'fines'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <AlertCircle className="w-4 h-4" />
          Fines & Infractions ({fines.length})
        </button>

        <button
          onClick={() => setActiveSubTab('payments')}
          className={`pb-3 transition-all cursor-pointer flex items-center gap-2 ${
            activeSubTab === 'payments'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <History className="w-4 h-4" />
          Payment Transactions ({payments.length})
        </button>
      </div>

      {/* SubTab 1: Member Balances */}
      {activeSubTab === 'overview' && (
        <Card className="p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Active Brotherhood Receivables</h3>
              <p className="text-xs text-slate-500">Breakdown of member balances, payment standing, and semester dues status.</p>
            </div>

            <div className="relative w-full sm:w-64">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
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
                  <th className="py-2.5 px-3">Standing</th>
                  <th className="py-2.5 px-3">Pledge Class</th>
                  <th className="py-2.5 px-3 text-right">Outstanding Balance</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredMembers.map(mem => {
                  const balanceCents = mem.duesBalanceCents !== undefined ? mem.duesBalanceCents : mem.duesBalance * 100;
                  const isDelinquent = balanceCents > 50000; // >$500

                  return (
                    <tr key={mem.id} className="hover:bg-slate-50/60">
                      <td className="py-3 px-3">
                        <div className="font-bold text-slate-900">{mem.name}</div>
                        <div className="text-xs text-slate-500">{mem.role}</div>
                      </td>
                      <td className="py-3 px-3">
                        <span className={`text-xs px-2 py-0.5 rounded font-semibold ${
                          mem.standing === 'Good Standing' 
                            ? 'bg-emerald-50 text-emerald-800' 
                            : 'bg-red-50 text-red-800'
                        }`}>
                          {mem.standing}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-slate-600">{mem.pledgeClass}</td>
                      <td className="py-3 px-3 text-right">
                        <span className={`font-mono font-bold text-xs ${
                          balanceCents > 0 ? 'text-red-600' : 'text-emerald-600'
                        }`}>
                          {formatMoney(balanceCents)}
                        </span>
                      </td>
                      <td className="py-3 px-3 text-right">
                        {balanceCents > 0 && isOfficer && (
                          <button
                            onClick={() => setPendingMarkPaid({ member: mem, balanceCents })}
                            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-800 font-semibold px-2 py-1 rounded transition-all cursor-pointer"
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
        <Card className="p-5 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
                Immutable Chapter Financial Ledger (`big_ledger`)
              </h3>
              <p className="text-xs text-slate-500">
                Permanent, append-only record. Entries cannot be edited or deleted. Corrections are recorded as linked offsetting adjustment transactions.
              </p>
            </div>

            <div className="flex gap-1 bg-slate-100 p-1 rounded-lg text-xs">
              {['ALL', 'DUES_CHARGE', 'FINE_CHARGE', 'PAYMENT_CREDIT', 'ADJUSTMENT_CORRECTION'].map(ft => (
                <button
                  key={ft}
                  onClick={() => setLedgerFilter(ft)}
                  className={`px-2 py-1 rounded font-semibold transition-all cursor-pointer ${
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
                  {isOfficer && <th className="py-2.5 px-3 text-right">Correction</th>}
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
                      {isOfficer && (
                        <td className="py-3 px-3 text-right">
                          <button
                            onClick={() => {
                              setShowCorrectionModal(entry);
                              setCorrectionAmountCents(-entry.amountCents);
                            }}
                            className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-2 py-1 rounded transition-all cursor-pointer flex items-center gap-1 ml-auto"
                            title="Post linked offsetting correction to immutable ledger"
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
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Disciplinary Fines & Violations</h3>
              <p className="text-xs text-slate-500">Issued for unexcused attendance or house rule infractions.</p>
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

                  {isOfficer && f.status === 'Unpaid' && (
                    <button
                      onClick={() => setPendingFinePaid(f)}
                      className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer"
                    >
                      Clear / Settle
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
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Payment Gateway Records</h3>
              <p className="text-xs text-slate-500">Real-time incoming ACH, card, and Venmo dues settlement receipts.</p>
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

      {/* MODAL: Issue Fine */}
      {showIssueFineModal && (
        <Modal>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-display font-bold text-base text-red-900 flex items-center gap-2">
                <AlertCircle className="w-5 h-5 text-red-600" />
                Issue Fine Citation
              </h3>
              <button onClick={() => setShowIssueFineModal(false)} className="text-slate-500 hover:text-slate-600 font-bold">✕</button>
            </div>

            <form onSubmit={handleIssueFineSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Select Brother</label>
                <select
                  value={selectedMemberId}
                  onChange={e => setSelectedMemberId(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-red-500"
                >
                  {members.map(m => (
                    <option key={m.id} value={m.id}>{m.name} ({m.role})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Fine Amount ($)</label>
                <input
                  type="number"
                  value={fineAmount}
                  onChange={e => setFineAmount(e.target.value)}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-red-500"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Reason & Bylaw Clause</label>
                <textarea
                  value={fineReason}
                  onChange={e => setFineReason(e.target.value)}
                  placeholder="e.g. Unexcused absence from Chapter Meeting (Bylaw II.C.4)"
                  rows={2}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-red-500"
                  required
                />
              </div>

              <button
                type="submit"
                className="w-full bg-red-600 hover:bg-red-700 text-white font-bold py-3 min-h-11 rounded-lg text-xs transition-all"
              >
                Assess Fine to Member Ledger
              </button>
            </form>
        </Modal>
      )}

      {/* MODAL: Pay Dues (Member) */}
      {showPayModal && currentMember && (
        <Modal>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2">
                <CreditCard className="w-5 h-5 text-gold" />
                Settle Dues / Fines Balance
              </h3>
              <button onClick={() => setShowPayModal(false)} className="text-slate-500 hover:text-slate-600 font-bold">✕</button>
            </div>

            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs mb-4">
              <div className="text-amber-900 font-bold">Current Outstanding Balance:</div>
              <div className="text-xl font-display font-black text-amber-900">
                {formatMoney(currentMember.duesBalanceCents || currentMember.duesBalance * 100)}
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
                  <option value="Venmo">Venmo Gateway</option>
                  <option value="Card">Debit / Credit Card</option>
                  <option value="Bank Transfer">ACH Bank Transfer</option>
                </select>
              </div>

              <button
                type="submit"
                className="w-full bg-gold hover:bg-[#c5a02b] text-navy font-bold py-3 min-h-11 rounded-lg text-xs transition-all"
              >
                Submit Payment Authorization
              </button>
            </form>
        </Modal>
      )}

      {/* MODAL: Post Immutable Ledger Linked Correction */}
      {showCorrectionModal && (
        <Modal>
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2">
                <RotateCcw className="w-5 h-5 text-purple-600" />
                Post Linked Ledger Correction
              </h3>
              <button onClick={() => setShowCorrectionModal(null)} className="text-slate-500 hover:text-slate-600 font-bold">✕</button>
            </div>

            <p className="text-xs text-slate-600 mb-3">
              Creating linked correction for Sequence #{showCorrectionModal.sequence} ({showCorrectionModal.description}).
            </p>

            <form onSubmit={handleCorrectionSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Adjustment Amount in Cents (e.g. -5000 for -$50.00)</label>
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
                Commit Linked Audit Adjustment
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

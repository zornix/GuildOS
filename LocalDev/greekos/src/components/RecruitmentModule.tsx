import React, { useState } from 'react';
import {
  UserPlus,
  Search,
  ThumbsUp,
  Plus,
  Phone,
  Send
} from 'lucide-react';
import { PNM } from '../types';
import Modal from './ui/Modal';
import Card from './ui/Card';
import ConfirmDialog from './ui/ConfirmDialog';

interface RecruitmentModuleProps {
  pnms: PNM[];
  isOfficer: boolean;
  onAddPNM: (pnm: Omit<PNM, 'id' | 'votesFor' | 'votesAgainst' | 'status'>) => void;
  onVotePNM: (pnmId: string, type: 'up' | 'down') => void;
  onExtendBid: (pnmId: string) => void;
}

export default function RecruitmentModule({
  pnms,
  isOfficer,
  onAddPNM,
  onVotePNM,
  onExtendBid
}: RecruitmentModuleProps) {
  const safePNMs = pnms || [];
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [pendingBid, setPendingBid] = useState<PNM | null>(null);

  // Form State
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [major, setMajor] = useState('');
  const [gpa, setGPA] = useState('3.5');
  const [year, setYear] = useState('Freshman');
  const [hometown, setHometown] = useState('');
  const [notes, setNotes] = useState('');

  const filteredPNMs = safePNMs.filter(p => {
    if (filterStatus !== 'ALL' && p.status !== filterStatus) return false;
    if (searchTerm) {
      const match = (p.name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                    (p.major || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                    (p.hometown || '').toLowerCase().includes(searchTerm.toLowerCase());
      if (!match) return false;
    }
    return true;
  });

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAddPNM({
      name,
      email,
      phone,
      major,
      gpa: parseFloat(gpa) || 3.0,
      year,
      hometown,
      notes,
      eventsAttended: 1
    });

    setName('');
    setEmail('');
    setPhone('');
    setMajor('');
    setHometown('');
    setNotes('');
    setShowAddModal(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <UserPlus className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Recruitment
            </h2>
            <span className="text-xs font-semibold bg-navy text-gold px-2 py-0.5 rounded-full">
              {pnms.length} tracked
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Track potential new members, vote on bids, and send invitations.
          </p>
        </div>

        <button
          onClick={() => setShowAddModal(true)}
          className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer w-full sm:w-auto justify-center"
        >
          <Plus className="w-4 h-4" />
          Add Prospect (PNM)
        </button>
      </div>

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {['ALL', 'Prospect', 'Rush Active', 'Bid Extended', 'Bid Accepted'].map(s => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-2.5 py-1 rounded-md font-semibold cursor-pointer transition-all ${
                filterStatus === s ? 'bg-navy text-gold' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            aria-label="Search prospects"
            placeholder="Search prospect..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-gold"
          />
        </div>
      </Card>

      {/* PNM Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredPNMs.map(pnm => {
          const totalVotes = pnm.votesFor + pnm.votesAgainst;
          const approvalPct = totalVotes > 0 ? Math.round((pnm.votesFor / totalVotes) * 100) : 0;

          return (
            <Card key={pnm.id} className="p-5 hover:border-gold transition-all space-y-4">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-display font-extrabold text-slate-900 text-base">{pnm.name}</h3>
                  <p className="text-xs text-slate-500">{pnm.major} &bull; {pnm.year}</p>
                </div>

                <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                  pnm.status === 'Bid Accepted' ? 'bg-emerald-100 text-emerald-800' :
                  pnm.status === 'Bid Extended' ? 'bg-gold/20 text-[#917215] border border-gold/40' :
                  'bg-blue-100 text-blue-800'
                }`}>
                  {pnm.status}
                </span>
              </div>

              <div className="text-xs text-slate-600 space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                <div className="flex justify-between">
                  <span className="text-slate-500">Hometown:</span>
                  <span className="font-semibold text-slate-800">{pnm.hometown}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">High School / Col GPA:</span>
                  <span className="font-semibold text-slate-800">{pnm.gpa}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Rush Events Attended:</span>
                  <span className="font-semibold text-slate-800">{pnm.eventsAttended} events</span>
                </div>
              </div>

              {pnm.notes && (
                <p className="text-xs text-slate-600 italic">
                  "{pnm.notes}"
                </p>
              )}

              {/* Voting Bar */}
              <div className="space-y-1.5 pt-2 border-t border-slate-100">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Brotherhood Votes:</span>
                  <span className="font-bold text-slate-800">{pnm.votesFor} For / {pnm.votesAgainst} Against ({approvalPct}%)</span>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onVotePNM(pnm.id, 'up')}
                    className="flex-1 py-1.5 rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 text-xs font-bold transition-all flex items-center justify-center gap-1 cursor-pointer"
                  >
                    <ThumbsUp className="w-3.5 h-3.5" /> +1 Vote For
                  </button>

                  <button
                    onClick={() => onVotePNM(pnm.id, 'down')}
                    className="py-1.5 px-3 rounded-lg border border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 text-xs font-bold transition-all cursor-pointer"
                  >
                    -1
                  </button>
                </div>

                {isOfficer && pnm.status !== 'Bid Extended' && pnm.status !== 'Bid Accepted' && (
                  <button
                    onClick={() => setPendingBid(pnm)}
                    className="w-full mt-2 bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs py-2 rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-2xs"
                  >
                    <Send className="w-3.5 h-3.5" /> Extend bid
                  </button>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      {/* MODAL: Add PNM */}
      {showAddModal && (
        <Modal title="Log Potential New Member (PNM)" onClose={() => setShowAddModal(false)}>

            <form onSubmit={handleAddSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Full Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="e.g. Gavin Henderson"
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="g.henderson@uni.edu"
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Phone</label>
                  <input
                    type="text"
                    value={phone}
                    onChange={e => setPhone(e.target.value)}
                    placeholder="(555) 302-8491"
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Major</label>
                  <input
                    type="text"
                    value={major}
                    onChange={e => setMajor(e.target.value)}
                    placeholder="Finance"
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">GPA</label>
                  <input
                    type="number"
                    step="0.01"
                    value={gpa}
                    onChange={e => setGPA(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Class Year</label>
                  <select
                    value={year}
                    onChange={e => setYear(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  >
                    <option value="Freshman">Freshman</option>
                    <option value="Sophomore">Sophomore</option>
                    <option value="Junior">Junior</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Hometown</label>
                <input
                  type="text"
                  value={hometown}
                  onChange={e => setHometown(e.target.value)}
                  placeholder="Austin, TX"
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Rush Committee Notes</label>
                <textarea
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  placeholder="Met at Rush BBQ, plays club soccer, strong fit with Alpha class..."
                  rows={2}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                />
              </div>

              <button
                type="submit"
                className="w-full bg-navy text-gold hover:bg-slate-800 font-bold py-3 min-h-11 rounded-lg text-xs transition-all"
              >
                Add to Rush Pipeline
              </button>
            </form>
        </Modal>
      )}

      {pendingBid && (
        <ConfirmDialog
          title="Extend a bid?"
          body={<p><strong>{pendingBid.name}</strong> moves to Bid Extended and gets a text saying the chapter has offered them membership.</p>}
          confirmLabel="Extend bid"
          onCancel={() => setPendingBid(null)}
          onConfirm={() => { onExtendBid(pendingBid.id); setPendingBid(null); }}
        />
      )}
    </div>
  );
}

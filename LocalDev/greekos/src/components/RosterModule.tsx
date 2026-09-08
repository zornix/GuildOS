import React, { useState } from 'react';
import {
  Users,
  Search,
  GraduationCap,
  Phone,
  Plus
} from 'lucide-react';
import { Member } from '../types';
import Modal from './ui/Modal';
import Card from './ui/Card';
import ConfirmDialog from './ui/ConfirmDialog';
import { formatMoney } from '../formatters';

interface RosterModuleProps {
  members: Member[];
  isOfficer: boolean;
  onAddMember: (member: Omit<Member, 'id' | 'points' | 'attendanceRate' | 'duesBalance' | 'duesBalanceCents' | 'securityHoursServed'>) => void;
  onUpdateStanding: (memberId: string, standing: 'Good Standing' | 'Academic Probation' | 'Social Suspension' | 'Financial Hold') => void;
}

export default function RosterModule({
  members,
  isOfficer,
  onAddMember,
  onUpdateStanding
}: RosterModuleProps) {
  const safeMembers = members || [];
  const [filterRole, setFilterRole] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedMember, setSelectedMember] = useState<Member | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [pendingStanding, setPendingStanding] = useState<{ member: Member; standing: Member['standing'] } | null>(null);

  // New Member Form State
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [role, setRole] = useState<Member['role']>('Active');
  const [pledgeClass, setPledgeClass] = useState('Fall 2026');
  const [major, setMajor] = useState('');
  const [gpa, setGPA] = useState('3.4');
  const [roomNumber, setRoomNumber] = useState('204');

  const filteredMembers = safeMembers.filter(m => {
    if (filterRole !== 'ALL' && m.role !== filterRole) return false;
    if (searchTerm) {
      const match = (m.name || '').toLowerCase().includes(searchTerm.toLowerCase()) || 
                    (m.major || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                    (m.role || '').toLowerCase().includes(searchTerm.toLowerCase());
      if (!match) return false;
    }
    return true;
  });

  const handleAddSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onAddMember({
      name,
      email,
      phone,
      role,
      status: role === 'Pledge' ? 'Pledge' : 'Active',
      pledgeClass,
      major,
      gpa: parseFloat(gpa) || 3.0,
      standing: 'Good Standing',
      roomNumber
    });

    setName('');
    setEmail('');
    setPhone('');
    setMajor('');
    setShowAddModal(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Users className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Roster
            </h2>
            <span className="text-xs font-semibold bg-navy text-gold px-2 py-0.5 rounded-full">
              {members.length} members
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Everyone on the chapter roll, from new pledges to officers.
          </p>
        </div>

        {isOfficer && (
          <button
            onClick={() => setShowAddModal(true)}
            className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-sm flex items-center gap-2 transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            Add Member
          </button>
        )}
      </div>

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col sm:flex-row gap-3 items-center justify-between">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {['ALL', 'President', 'Treasurer', 'Risk Manager', 'Active', 'Pledge'].map(r => (
            <button
              key={r}
              onClick={() => setFilterRole(r)}
              className={`px-2.5 py-1 rounded-md font-semibold cursor-pointer transition-all ${
                filterRole === r ? 'bg-navy text-gold' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {r}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search roster..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:border-gold"
          />
        </div>
      </Card>

      {/* Roster Table */}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 text-xs">
              <tr>
                <th className="py-3 px-4">Brother & Role</th>
                <th className="py-3 px-4">Pledge Class</th>
                <th className="py-3 px-4">Academic Standing</th>
                {/* Attendance rates are for the member themself and officers only. */}
                {isOfficer && <th className="py-3 px-4">Attendance</th>}
                <th className="py-3 px-4">Unpaid fines</th>
                <th className="py-3 px-4">Risk Shifts</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredMembers.map(mem => {
                const isProbation = mem.standing !== 'Good Standing';

                return (
                  <tr key={mem.id} className="hover:bg-slate-50/60">
                    <td className="py-3 px-4">
                      <div className="font-bold text-slate-900 text-sm">{mem.name}</div>
                      <div className="text-xs text-gold-muted font-semibold">{mem.role}</div>
                      <div className="text-xs text-slate-500">{mem.major} &bull; Room {mem.roomNumber || 'N/A'}</div>
                    </td>

                    <td className="py-3 px-4 text-slate-600">
                      {mem.pledgeClass}
                    </td>

                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5">
                        <GraduationCap className="w-3.5 h-3.5 text-slate-500" />
                        <span className="font-bold text-slate-800">{mem.gpa} GPA</span>
                      </div>
                      <span className={`text-xs font-bold px-1.5 py-0.2 rounded mt-0.5 inline-block ${
                        mem.standing === 'Good Standing' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800'
                      }`}>
                        {mem.standing}
                      </span>
                    </td>

                    {isOfficer && (
                      <td className="py-3 px-4 font-bold text-slate-800">
                        <span className={mem.attendanceRate >= 85 ? 'text-emerald-600' : 'text-red-600'}>
                          {mem.attendanceRate}%
                        </span>
                      </td>
                    )}

                    <td className="py-3 px-4 font-mono font-bold">
                      <span className={mem.duesBalance > 0 ? 'text-red-600' : 'text-emerald-600'}>
                        {formatMoney(mem.duesBalanceCents || mem.duesBalance * 100)}
                      </span>
                    </td>

                    <td className="py-3 px-4 text-slate-600">
                      {mem.securityHoursServed || 0} hrs
                    </td>

                    <td className="py-3 px-4 text-right">
                      {isOfficer && (
                        <select
                          value={mem.standing}
                          onChange={e => setPendingStanding({ member: mem, standing: e.target.value as Member['standing'] })}
                          className="text-xs border border-slate-200 rounded p-1 bg-white cursor-pointer"
                        >
                          <option value="Good Standing">Good Standing</option>
                          <option value="Academic Probation">Academic Probation</option>
                          <option value="Social Suspension">Social Suspension</option>
                          <option value="Financial Hold">Financial Hold</option>
                        </select>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* MODAL: Add Member */}
      {showAddModal && (
        <Modal>
            <div className="flex justify-between items-center mb-4 border-b border-slate-100 pb-3">
              <h3 className="font-display font-extrabold text-base text-slate-900 flex items-center gap-2">
                <Users className="w-5 h-5 text-gold" />
                Enroll New Brother on Roster
              </h3>
              <button onClick={() => setShowAddModal(false)} className="text-slate-500 hover:text-slate-600 font-bold">✕</button>
            </div>

            <form onSubmit={handleAddSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Full Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="e.g. Samuel Bennett"
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
                    placeholder="s.bennett@university.edu"
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
                    placeholder="(555) 019-2834"
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Chapter Role</label>
                  <select
                    value={role}
                    onChange={e => setRole(e.target.value as any)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  >
                    <option value="Active">Active Brother</option>
                    <option value="Pledge">New Pledge</option>
                    <option value="Risk Manager">Risk Manager</option>
                    <option value="Secretary">Secretary</option>
                    <option value="Pledge Educator">Pledge Educator</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Pledge Class</label>
                  <input
                    type="text"
                    value={pledgeClass}
                    onChange={e => setPledgeClass(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Major</label>
                  <input
                    type="text"
                    value={major}
                    onChange={e => setMajor(e.target.value)}
                    placeholder="Economics"
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-700 block mb-1">Cumulative GPA</label>
                  <input
                    type="number"
                    step="0.01"
                    value={gpa}
                    onChange={e => setGPA(e.target.value)}
                    className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                    required
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full bg-navy text-gold hover:bg-slate-800 font-bold py-3 min-h-11 rounded-lg text-xs transition-all mt-2 cursor-pointer"
              >
                Add Brother to Roster
              </button>
            </form>
        </Modal>
      )}

      {pendingStanding && (
        <ConfirmDialog
          title="Change standing?"
          tone="danger"
          body={<p><strong>{pendingStanding.member.name}</strong>: {pendingStanding.member.standing} &rarr; <strong>{pendingStanding.standing}</strong>. Standing affects what they may do in the chapter.</p>}
          confirmLabel="Change standing"
          onCancel={() => setPendingStanding(null)}
          onConfirm={() => { onUpdateStanding(pendingStanding.member.id, pendingStanding.standing); setPendingStanding(null); }}
        />
      )}
    </div>
  );
}

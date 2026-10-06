import { useState } from 'react';
import {
  Users,
  Search,
  GraduationCap
} from 'lucide-react';
import { Member } from '../types';
import type { RosterImportResult } from '../api';
import RosterCsvImport from './roster/RosterCsvImport';
import MemberRolesPanel from './MemberRolesPanel';
import Card from './ui/Card';
import { formatMoney } from '../formatters';

interface RosterModuleProps {
  members: Member[];
  /** `members:invite` — the CSV roster import. */
  canInviteMembers: boolean;
  /** `standing:view_all` — the chapter-wide attendance column. */
  canSeeStandingDetail: boolean;
  /** `roles:assign` — gates the per-member role toggles. */
  canAssignRoles: boolean;
  /** `members:invite` — gates the per-member announcement-texts indicator (#57). */
  canSeeSmsConsent: boolean;
  onRolesChanged?: (memberId: string) => void;
  onImportRoster?: (file: File) => Promise<RosterImportResult>;
}

export default function RosterModule({
  members,
  canInviteMembers,
  canSeeStandingDetail,
  canAssignRoles,
  canSeeSmsConsent,
  onRolesChanged,
  onImportRoster
}: RosterModuleProps) {
  const safeMembers = members || [];
  const [filterRole, setFilterRole] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [rolesMember, setRolesMember] = useState<Member | null>(null);
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
      </div>

      {canInviteMembers && onImportRoster && <RosterCsvImport onImport={onImportRoster} />}

      {/* Filter and Search Bar */}
      <Card className="p-4 flex flex-col sm:flex-row gap-3 sm:items-center justify-between">
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {['ALL', 'President', 'Treasurer', 'Risk Manager', 'Active', 'Pledge'].map(r => (
            <button
              key={r}
              onClick={() => setFilterRole(r)}
              className={`px-2.5 py-1 min-h-11 sm:min-h-0 rounded-md font-semibold cursor-pointer transition-all ${
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
            aria-label="Search roster"
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
                <th className="py-3 px-4 hidden md:table-cell">Pledge Class</th>
                <th className="py-3 px-4 hidden sm:table-cell">Academic Standing</th>
                {/* Attendance rates are for the member themself and officers only. */}
                {canSeeStandingDetail && <th className="py-3 px-4 hidden md:table-cell">Attendance</th>}
                <th className="py-3 px-4">Unpaid fines</th>
                <th className="py-3 px-4 hidden md:table-cell">Risk Shifts</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredMembers.map(mem => {
                return (
                  <tr key={mem.id} className="hover:bg-slate-50/60">
                    <td className="py-3 px-4">
                      <div className="font-bold text-slate-900 text-sm">{mem.name}</div>
                      <div className="text-xs text-gold-muted font-semibold">{mem.role}</div>
                      <div className="text-xs text-slate-500">{mem.major} &bull; Room {mem.roomNumber || 'N/A'}</div>
                      {canSeeSmsConsent && (
                        <div
                          className="text-xs text-slate-500 flex items-center gap-1.5 mt-0.5"
                          title={`Announcement texts are ${mem.smsConsent ? 'on' : 'off'} for ${mem.name}. Everything else is emailed.`}
                        >
                          <span
                            aria-hidden="true"
                            className={`w-2 h-2 rounded-full ${mem.smsConsent ? 'bg-emerald-500' : 'bg-slate-300'}`}
                          />
                          Announcement texts: {mem.smsConsent ? 'on' : 'off'}
                        </div>
                      )}
                    </td>

                    <td className="py-3 px-4 text-slate-600 hidden md:table-cell">
                      {mem.pledgeClass}
                    </td>

                    <td className="py-3 px-4 hidden sm:table-cell">
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

                    {canSeeStandingDetail && (
                      <td className="py-3 px-4 font-bold text-slate-800 hidden md:table-cell">
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

                    <td className="py-3 px-4 text-slate-600 hidden md:table-cell">
                      {mem.securityHoursServed || 0} hrs
                    </td>

                    <td className="py-3 px-4 text-right">
                      <div className="flex flex-wrap items-center justify-end gap-2">
                      {canAssignRoles && (
                        <button
                          type="button"
                          onClick={() => setRolesMember(mem)}
                          className="text-xs font-semibold border border-slate-200 rounded px-2 py-1 min-h-11 sm:min-h-0 sm:py-1 hover:bg-slate-100 cursor-pointer"
                        >
                          Roles
                        </button>
                      )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {rolesMember && (
        <MemberRolesPanel
          memberId={rolesMember.id}
          memberName={rolesMember.name}
          onRolesChanged={onRolesChanged}
          onClose={() => setRolesMember(null)}
        />
      )}
    </div>
  );
}

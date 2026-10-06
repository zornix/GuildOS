import React, { useEffect, useState } from 'react';
import {
  UserCheck,
  Check,
  X,
  KeyRound,
  FileText,
  CheckCircle2
} from 'lucide-react';
import { ChapterEvent, Member, Excuse } from '../types';
import Modal from './ui/Modal';
import Card from './ui/Card';
import { RollStatus, markRemainingPresent, nextStatus, rollCallSummary } from '../lib/rollCall';
import DoorCodeField from './home/DoorCodeField';

interface AttendanceModuleProps {
  events: ChapterEvent[];
  members: Member[];
  excuses: Excuse[];
  /** `attendance:override` — the manual roll-call marks. */
  canMarkAttendance: boolean;
  /** `attendance:excuse:review` — approve or reject a submitted excuse. */
  canReviewExcuses: boolean;
  /** `standing:view_all` — the chapter-wide semester rates. */
  canSeeAttendanceRates: boolean;
  currentMemberName: string;
  /** Roll-call markers land on roll call; everyone else lands on the door code. */
  initialTab: 'roster_check' | 'excuses' | 'self_pin';
  onRecordAttendance: (eventId: string, records: { memberId: string; status: 'Present' | 'Absent' | 'Excused' | 'Late' }[]) => void;
  onSubmitExcuse: (excuse: Omit<Excuse, 'id' | 'status' | 'submittedDate'>) => void;
  onReviewExcuse: (excuseId: string, status: 'Approved' | 'Rejected', reviewedBy: string) => void;
  /** The door code identifies the event; the backend checks in the signed-in member. */
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
}

const ROLL_OPTIONS = ['Present', 'Late', 'Excused', 'Absent'] as const;

export default function AttendanceModule({
  events,
  members,
  excuses,
  canMarkAttendance,
  canReviewExcuses,
  canSeeAttendanceRates,
  currentMemberName,
  initialTab,
  onRecordAttendance,
  onSubmitExcuse,
  onReviewExcuse,
  onSelfCheckIn
}: AttendanceModuleProps) {
  const safeEvents = events || [];
  const safeMembers = members || [];
  const safeExcuses = excuses || [];

  const [selectedEventId, setSelectedEventId] = useState<string>(safeEvents[0]?.id || '');
  const [activeTab, setActiveTab] = useState<'roster_check' | 'excuses' | 'self_pin'>(initialTab);
  const [showExcuseModal, setShowExcuseModal] = useState(false);

  // Excuse Form State
  const [excuseEventId, setExcuseEventId] = useState(safeEvents[0]?.id || '');
  const [excuseReason, setExcuseReason] = useState('');

  // Attendance Sheet state for selected event
  const selectedEvent = safeEvents.find(e => e.id === selectedEventId) || safeEvents[0];
  const currentMember = safeMembers.find(m => m.name === currentMemberName);

  // Local attendance state for the roll call sheet. Marks belong to one event,
  // so switching the selector starts a fresh sheet rather than carrying them over.
  const [attendanceRecords, setAttendanceRecords] = useState<Record<string, RollStatus>>({});
  useEffect(() => setAttendanceRecords({}), [selectedEventId]);

  const handleStatusChange = (memberId: string, status: RollStatus) => {
    setAttendanceRecords(prev => ({
      ...prev,
      [memberId]: status
    }));
  };

  /** Arrow keys select within the row (Tab leaves it); focus follows the mark. */
  const moveStatus = (e: React.KeyboardEvent<HTMLButtonElement>, memberId: string, current: RollStatus | undefined) => {
    const next = nextStatus(current, e.key, ROLL_OPTIONS);
    if (!next) return;
    e.preventDefault();
    handleStatusChange(memberId, next);
    e.currentTarget.parentElement?.querySelector<HTMLElement>(`[data-status="${next}"]`)?.focus();
  };

  const summary = rollCallSummary(safeMembers, attendanceRecords);

  const handleSaveAttendance = () => {
    if (!selectedEvent || summary.marked.length === 0) return;
    onRecordAttendance(selectedEvent.id, summary.marked);
  };

  const handleExcuseSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentMember || !excuseReason.trim()) return;

    const ev = safeEvents.find(ev => ev.id === excuseEventId);
    onSubmitExcuse({
      memberId: currentMember.id,
      memberName: currentMember.name,
      eventId: excuseEventId,
      eventName: ev ? ev.title : 'Chapter Event',
      eventTitle: ev ? ev.title : 'Chapter Event',
      eventDate: ev ? ev.date : '2026-07-16',
      reason: excuseReason,
      submittedAt: new Date().toISOString()
    });

    setExcuseReason('');
    setShowExcuseModal(false);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <UserCheck className="w-6 h-6 text-gold" />
            <h2 className="text-2xl font-display font-extrabold text-slate-900 tracking-tight">
              Attendance
            </h2>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Take roll call, check members in at the door, and review excuses.
          </p>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setShowExcuseModal(true)}
            className="bg-white hover:bg-slate-50 text-slate-800 border border-slate-200 font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-xs flex items-center gap-2 transition-all cursor-pointer"
          >
            <FileText className="w-4 h-4 text-gold" />
            Request excuse
          </button>
        </div>
      </div>

      {/* Navigation subtabs */}
      <div className="flex border-b border-slate-200 gap-4 sm:gap-6 text-sm font-semibold overflow-x-auto">
        <button
          onClick={() => setActiveTab('roster_check')}
          className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === 'roster_check'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <UserCheck className="w-4 h-4" />
          Roll call
        </button>

        <button
          onClick={() => setActiveTab('self_pin')}
          className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === 'self_pin'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <KeyRound className="w-4 h-4" />
          Door code
        </button>

        <button
          onClick={() => setActiveTab('excuses')}
          className={`pb-3 shrink-0 whitespace-nowrap transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === 'excuses'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <FileText className="w-4 h-4" />
          Excuses ({safeExcuses.filter(e => e.status === 'Pending').length} pending)
        </button>
      </div>

      {/* TAB 1: Roll call */}
      {activeTab === 'roster_check' && (
        <Card className="p-4 sm:p-6 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
            <div>
              <span className="text-xs text-slate-500 font-bold block">Select Chapter Event</span>
              <select
                value={selectedEventId}
                onChange={e => setSelectedEventId(e.target.value)}
                className="max-w-full font-display font-bold text-slate-900 text-base border-none focus:outline-none cursor-pointer bg-transparent"
              >
                {safeEvents.map(ev => (
                  <option key={ev.id} value={ev.id}>
                    {ev.title} &bull; {ev.date} ({ev.type})
                  </option>
                ))}
              </select>
            </div>

            {canMarkAttendance && (
              <div className="flex flex-col sm:items-end gap-2">
                <div className="flex flex-wrap gap-2">
                  {summary.unmarked > 0 && (
                    <button
                      type="button"
                      onClick={() => setAttendanceRecords(markRemainingPresent(safeMembers, attendanceRecords))}
                      className="bg-white hover:bg-slate-50 text-slate-800 border border-slate-200 font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg shadow-xs cursor-pointer"
                    >
                      Mark remaining present ({summary.unmarked})
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={handleSaveAttendance}
                    disabled={summary.marked.length === 0}
                    className="bg-navy hover:bg-slate-800 text-gold font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg transition-all cursor-pointer flex items-center gap-2 shadow-xs disabled:opacity-50"
                  >
                    <CheckCircle2 className="w-4 h-4" />
                    Save roll call
                  </button>
                </div>
                <p role="status" className="text-xs text-slate-600">{summary.label || 'Nothing marked yet'}</p>
              </div>
            )}
          </div>

          {/* Roll Call Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-y border-slate-200 text-slate-600 text-xs">
                <tr>
                  <th className="py-2.5 px-2 sm:px-3">Brother</th>
                  <th className="py-2.5 px-3 hidden sm:table-cell">Role</th>
                  {/* Attendance rates are for the member themself and officers only. */}
                  {canSeeAttendanceRates && <th className="py-2.5 px-3 hidden sm:table-cell">Semester rate</th>}
                  <th className="py-2.5 px-2 sm:px-3 text-right">Attendance Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {safeMembers.map(mem => {
                  const status = attendanceRecords[mem.id];

                  return (
                    <tr key={mem.id} className="hover:bg-slate-50/60">
                      <td className="py-3 px-2 sm:px-3">
                        <span className="font-bold text-slate-900">{mem.name}</span>
                      </td>
                      <td className="py-3 px-3 text-slate-500 hidden sm:table-cell">{mem.role}</td>
                      {canSeeAttendanceRates && (
                        <td className="py-3 px-3 hidden sm:table-cell">
                          <span className={`font-bold ${
                            mem.attendanceRate >= 85 ? 'text-emerald-600' : 'text-red-600'
                          }`}>
                            {mem.attendanceRate}%
                          </span>
                        </td>
                      )}
                      <td className="py-3 px-2 sm:px-3 text-right">
                        {!status && <span className="sr-only sm:not-sr-only sm:inline text-xs text-slate-400 mr-2">Unmarked</span>}
                        <div
                          role="radiogroup"
                          aria-label={`Attendance for ${mem.name}`}
                          className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs font-semibold"
                        >
                          {ROLL_OPTIONS.map((st, idx) => {
                            const isCur = status === st;
                            return (
                              <button
                                key={st}
                                type="button"
                                role="radio"
                                aria-checked={isCur}
                                tabIndex={isCur || (!status && idx === 0) ? 0 : -1}
                                data-status={st}
                                disabled={!canMarkAttendance}
                                onClick={() => handleStatusChange(mem.id, st)}
                                onKeyDown={e => moveStatus(e, mem.id, status)}
                                className={`px-1.5 sm:px-2.5 py-1 min-h-11 sm:min-h-0 rounded-md transition-all cursor-pointer ${
                                  isCur 
                                    ? st === 'Present' 
                                      ? 'bg-emerald-600 text-white shadow-2xs' 
                                      : st === 'Absent' 
                                      ? 'bg-red-600 text-white shadow-2xs'
                                      : st === 'Excused'
                                      ? 'bg-blue-600 text-white shadow-2xs'
                                      : 'bg-amber-500 text-white shadow-2xs'
                                    : 'text-slate-600 hover:text-slate-900'
                                }`}
                              >
                                {st}
                              </button>
                            );
                          })}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* TAB 2: Door code */}
      {activeTab === 'self_pin' && (
        <Card className="p-4 sm:p-6 max-w-lg mx-auto text-center space-y-6">
          <div className="space-y-1">
            <div className="w-12 h-12 rounded-2xl bg-amber-50 text-gold flex items-center justify-center mx-auto mb-2 border border-amber-200">
              <KeyRound className="w-6 h-6" />
            </div>
            <h3 className="font-display font-extrabold text-slate-900 text-lg">
              Door code
            </h3>
            <p className="text-xs text-slate-500">
              Enter the door code an officer is showing. The code decides which event you are checked into.
            </p>
          </div>

          <DoorCodeField onSelfCheckIn={onSelfCheckIn} />
        </Card>
      )}

      {/* TAB 3: Excuses */}
      {activeTab === 'excuses' && (
        <Card className="p-4 sm:p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Submitted Excuse Requests</h3>
              <p className="text-xs text-slate-500">Officers review these.</p>
            </div>
          </div>

          <div className="divide-y divide-slate-100">
            {excuses.length === 0 ? (
              <p className="text-xs text-slate-500 py-6 text-center italic">No excuse requests on file.</p>
            ) : (
              excuses.map(excuse => (
                <div key={excuse.id} className="py-4 flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-sm text-slate-900">{excuse.memberName}</span>
                      <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                        excuse.status === 'Approved' 
                          ? 'bg-emerald-100 text-emerald-800' 
                          : excuse.status === 'Rejected' 
                          ? 'bg-red-100 text-red-800' 
                          : 'bg-amber-100 text-amber-800'
                      }`}>
                        {excuse.status}
                      </span>
                    </div>

                    <div className="text-xs text-slate-500">
                      Event: <strong className="text-slate-800">{excuse.eventName || excuse.eventTitle}</strong> &bull; {excuse.eventDate}
                    </div>

                    <p className="text-xs text-slate-700 bg-slate-50 p-2.5 rounded-lg border border-slate-200/80 mt-1.5">
                      "{excuse.reason}"
                    </p>
                  </div>

                  {/* Officer Actions */}
                  {canReviewExcuses && excuse.status === 'Pending' && (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => onReviewExcuse(excuse.id, 'Approved', currentMemberName)}
                        className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 min-h-11 sm:min-h-0 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1"
                      >
                        <Check className="w-3.5 h-3.5" />
                        Approve
                      </button>

                      <button
                        onClick={() => onReviewExcuse(excuse.id, 'Rejected', currentMemberName)}
                        className="text-xs bg-red-600 hover:bg-red-700 text-white font-bold px-3 py-1.5 min-h-11 sm:min-h-0 rounded-lg transition-all cursor-pointer flex items-center justify-center gap-1"
                      >
                        <X className="w-3.5 h-3.5" />
                        Reject
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </Card>
      )}

      {/* MODAL: Submit Excuse */}
      {showExcuseModal && (
        <Modal title="Request an excuse" onClose={() => setShowExcuseModal(false)}>

            <form onSubmit={handleExcuseSubmit} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Select Event</label>
                <select
                  value={excuseEventId}
                  onChange={e => setExcuseEventId(e.target.value)}
                  className="w-full text-xs border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                >
                  {events.map(ev => (
                    <option key={ev.id} value={ev.id}>
                      {ev.title} ({ev.date})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-xs font-semibold text-slate-700 block mb-1">Detailed Explanation & Reason</label>
                <textarea
                  value={excuseReason}
                  onChange={e => setExcuseReason(e.target.value)}
                  placeholder="e.g. Midterm exam conflict with CHEM 2301 from 6:30-8:00pm. Have syllabus proof available."
                  rows={3}
                  className="w-full text-sm border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-gold"
                  required
                />
              </div>

              <button
                type="submit"
                className="w-full bg-navy text-gold hover:bg-slate-800 font-bold py-3 min-h-11 rounded-lg text-xs transition-all"
              >
                Submit request
              </button>
            </form>
        </Modal>
      )}
    </div>
  );
}

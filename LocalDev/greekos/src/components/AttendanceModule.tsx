import React, { useState } from 'react';
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
import { RollStatus, markRemainingPresent, rollCallSummary } from '../lib/rollCall';

interface AttendanceModuleProps {
  events: ChapterEvent[];
  members: Member[];
  excuses: Excuse[];
  isOfficer: boolean;
  currentMemberName: string;
  onRecordAttendance: (eventId: string, records: { memberId: string; status: 'Present' | 'Absent' | 'Excused' | 'Late' }[]) => void;
  onSubmitExcuse: (excuse: Omit<Excuse, 'id' | 'status' | 'submittedDate'>) => void;
  onReviewExcuse: (excuseId: string, status: 'Approved' | 'Rejected', reviewedBy: string) => void;
  /** The door code identifies the event; the backend checks in the signed-in member. */
  onSelfCheckIn: (code: string) => Promise<{ ok: boolean; message: string }>;
}

export default function AttendanceModule({
  events,
  members,
  excuses,
  isOfficer,
  currentMemberName,
  onRecordAttendance,
  onSubmitExcuse,
  onReviewExcuse,
  onSelfCheckIn
}: AttendanceModuleProps) {
  const safeEvents = events || [];
  const safeMembers = members || [];
  const safeExcuses = excuses || [];

  const [selectedEventId, setSelectedEventId] = useState<string>(safeEvents[0]?.id || '');
  const [activeTab, setActiveTab] = useState<'roster_check' | 'excuses' | 'self_pin'>('roster_check');
  const [showExcuseModal, setShowExcuseModal] = useState(false);

  // Door-code check-in state
  const [enteredCode, setEnteredCode] = useState('');
  const [codeFeedback, setCodeFeedback] = useState<{ success?: boolean; msg?: string } | null>(null);
  const [checkingIn, setCheckingIn] = useState(false);

  // Excuse Form State
  const [excuseEventId, setExcuseEventId] = useState(safeEvents[0]?.id || '');
  const [excuseReason, setExcuseReason] = useState('');

  // Attendance Sheet state for selected event
  const selectedEvent = safeEvents.find(e => e.id === selectedEventId) || safeEvents[0];
  const currentMember = safeMembers.find(m => m.name === currentMemberName);

  // Local attendance state for the roll call sheet
  const [attendanceRecords, setAttendanceRecords] = useState<Record<string, RollStatus>>({});

  const handleStatusChange = (memberId: string, status: RollStatus) => {
    setAttendanceRecords(prev => ({
      ...prev,
      [memberId]: status
    }));
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

  const handleCodeCheckInSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCheckingIn(true);
    const result = await onSelfCheckIn(enteredCode);
    setCheckingIn(false);
    setCodeFeedback({ success: result.ok, msg: result.message });
    if (result.ok) setEnteredCode('');
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
            Submit Excuse Request
          </button>
        </div>
      </div>

      {/* Navigation subtabs */}
      <div className="flex border-b border-slate-200 gap-6 text-sm font-semibold">
        <button
          onClick={() => setActiveTab('roster_check')}
          className={`pb-3 transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === 'roster_check'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <UserCheck className="w-4 h-4" />
          Roll Call Sheet
        </button>

        <button
          onClick={() => setActiveTab('self_pin')}
          className={`pb-3 transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === 'self_pin'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <KeyRound className="w-4 h-4" />
          Live Door Check-In
        </button>

        <button
          onClick={() => setActiveTab('excuses')}
          className={`pb-3 transition-all cursor-pointer flex items-center gap-2 ${
            activeTab === 'excuses'
              ? 'text-navy border-b-2 border-gold font-bold'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          <FileText className="w-4 h-4" />
          Excuse Approvals ({safeExcuses.filter(e => e.status === 'Pending').length} Pending)
        </button>
      </div>

      {/* TAB 1: Roll Call Sheet */}
      {activeTab === 'roster_check' && (
        <Card className="p-6 space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
            <div>
              <span className="text-xs text-slate-500 font-bold block">Select Chapter Event</span>
              <select
                value={selectedEventId}
                onChange={e => setSelectedEventId(e.target.value)}
                className="font-display font-bold text-slate-900 text-base border-none focus:outline-none cursor-pointer bg-transparent"
              >
                {safeEvents.map(ev => (
                  <option key={ev.id} value={ev.id}>
                    {ev.title} &bull; {ev.date} ({ev.type})
                  </option>
                ))}
              </select>
            </div>

            {isOfficer && (
              <div className="flex flex-col sm:items-end gap-2">
                <div className="flex gap-2">
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
                  <th className="py-2.5 px-3">Brother</th>
                  <th className="py-2.5 px-3">Role</th>
                  {/* Attendance rates are for the member themself and officers only. */}
                  {isOfficer && <th className="py-2.5 px-3">Semester rate</th>}
                  <th className="py-2.5 px-3 text-right">Attendance Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {safeMembers.map(mem => {
                  const status = attendanceRecords[mem.id];

                  return (
                    <tr key={mem.id} className="hover:bg-slate-50/60">
                      <td className="py-3 px-3">
                        <span className="font-bold text-slate-900">{mem.name}</span>
                      </td>
                      <td className="py-3 px-3 text-slate-500">{mem.role}</td>
                      {isOfficer && (
                        <td className="py-3 px-3">
                          <span className={`font-bold ${
                            mem.attendanceRate >= 85 ? 'text-emerald-600' : 'text-red-600'
                          }`}>
                            {mem.attendanceRate}%
                          </span>
                        </td>
                      )}
                      <td className="py-3 px-3 text-right">
                        {!status && <span className="text-xs text-slate-400 mr-2">Unmarked</span>}
                        <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs font-semibold">
                          {(['Present', 'Late', 'Excused', 'Absent'] as const).map(st => {
                            const isCur = status === st;
                            return (
                              <button
                                key={st}
                                disabled={!isOfficer}
                                onClick={() => handleStatusChange(mem.id, st)}
                                className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
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

      {/* TAB 2: Live Door Check-In */}
      {activeTab === 'self_pin' && (
        <Card className="p-6 max-w-lg mx-auto text-center space-y-6">
          <div className="space-y-1">
            <div className="w-12 h-12 rounded-2xl bg-amber-50 text-gold flex items-center justify-center mx-auto mb-2 border border-amber-200">
              <KeyRound className="w-6 h-6" />
            </div>
            <h3 className="font-display font-extrabold text-slate-900 text-lg">
              Live Door Check-In
            </h3>
            <p className="text-xs text-slate-500">
              Enter the door code an officer is showing in Live Door Mode. The code decides
              which event you are checked into, so no event picker here.
            </p>
          </div>

          <form onSubmit={handleCodeCheckInSubmit} className="space-y-4">
            <div>
              <label className="text-xs font-bold text-slate-700 block mb-2">
                Door code
              </label>
              <input
                type="text"
                maxLength={6}
                value={enteredCode}
                onChange={e => setEnteredCode(e.target.value)}
                placeholder="A7x9Kp"
                className="w-48 mx-auto text-center text-3xl font-mono font-black tracking-widest py-3 border-2 border-slate-300 rounded-xl focus:outline-none focus:border-gold"
                required
              />
            </div>

            {codeFeedback && (
              <div className={`p-3 rounded-lg text-xs font-semibold ${
                codeFeedback.success ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-red-50 text-red-800 border border-red-200'
              }`}>
                {codeFeedback.msg}
              </div>
            )}

            <button
              type="submit"
              disabled={checkingIn || !enteredCode.trim()}
              className="w-full bg-navy text-gold hover:bg-slate-800 font-bold py-3 min-h-11 rounded-lg text-xs transition-all cursor-pointer disabled:opacity-50"
            >
              {checkingIn ? 'Checking in…' : 'Verify Attendance Check-In'}
            </button>
          </form>
        </Card>
      )}

      {/* TAB 3: Excuse Approvals */}
      {activeTab === 'excuses' && (
        <Card className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-slate-900 text-base">Submitted Excuse Requests</h3>
              <p className="text-xs text-slate-500">Executive board review for academic, medical, and family obligations.</p>
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
                  {isOfficer && excuse.status === 'Pending' && (
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => onReviewExcuse(excuse.id, 'Approved', currentMemberName)}
                        className="text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1"
                      >
                        <Check className="w-3.5 h-3.5" />
                        Approve
                      </button>

                      <button
                        onClick={() => onReviewExcuse(excuse.id, 'Rejected', currentMemberName)}
                        className="text-xs bg-red-600 hover:bg-red-700 text-white font-bold px-3 py-1.5 rounded-lg transition-all cursor-pointer flex items-center gap-1"
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
        <Modal>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-display font-bold text-base text-slate-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-gold" />
                Submit Absence Excuse Request
              </h3>
              <button onClick={() => setShowExcuseModal(false)} className="text-slate-500 hover:text-slate-600 font-bold">✕</button>
            </div>

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
                Submit for Executive Review
              </button>
            </form>
        </Modal>
      )}
    </div>
  );
}

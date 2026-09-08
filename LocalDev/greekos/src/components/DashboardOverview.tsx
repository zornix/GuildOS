import React, { useState } from 'react';
import {
  Users,
  Calendar,
  DollarSign,
  CheckSquare,
  AlertTriangle,
  Sparkles,
  CheckCircle2,
  Clock,
  Megaphone,
  CreditCard,
  X
} from 'lucide-react';
import { ChapterEvent, Member, Task, Fine, Initiative, Announcement, LedgerEntry } from '../types';
import Card from './ui/Card';
import ConfirmDialog from './ui/ConfirmDialog';
import { formatMoney, isoDay } from '../formatters';

interface DashboardOverviewProps {
  members: Member[];
  events: ChapterEvent[];
  tasks: Task[];
  fines: Fine[];
  initiatives: Initiative[];
  announcements: Announcement[];
  ledger: LedgerEntry[];
  isOfficer: boolean;
  currentMemberName: string;
  onNavigateTab: (tab: string) => void;
  onVolunteerOrganizer: (eventId: string, memberName: string) => void;
  onPayDuesQuick: () => void;
  onDeleteAnnouncement: (announcementId: string) => void;
}

export default function DashboardOverview({
  members,
  events,
  tasks,
  fines,
  initiatives,
  announcements,
  ledger,
  isOfficer,
  currentMemberName,
  onNavigateTab,
  onVolunteerOrganizer,
  onPayDuesQuick,
  onDeleteAnnouncement
}: DashboardOverviewProps) {
  const safeMembers = members || [];
  const safeEvents = events || [];
  const safeTasks = tasks || [];
  const safeInitiatives = initiatives || [];
  const safeAnnouncements = announcements || [];
  const safeLedger = ledger || [];

  const currentMember = safeMembers.find(m => m.name === currentMemberName);

  const [pendingDelete, setPendingDelete] = useState<Announcement | null>(null);

  // Computations
  const totalReceivablesCents = safeMembers.reduce((sum, m) => sum + (m.duesBalanceCents || Math.round((m.duesBalance || 0) * 100)), 0);
  const avgAttendance = Math.round(safeMembers.reduce((sum, m) => sum + (m.attendanceRate || 0), 0) / (safeMembers.length || 1));
  const activeMembersCount = safeMembers.filter(m => m.role !== 'Pledge' && m.role !== 'Alumni').length;
  const pendingTasks = safeTasks.filter(t => t.status !== 'Completed').length;
  const today = isoDay();
  const upcomingEvents = safeEvents.filter(e => e.date >= today).slice(0, 3);

  // Personal strip (members): jobs this member has claimed across all events.
  const myClaimedJobs = currentMember
    ? safeEvents.flatMap(e => e.jobs || []).filter(j => (j.claimants || []).some(c => c.memberId === currentMember.id)).length
    : 0;

  // Pending officer sign-offs
  const pendingJobSignOffs = safeEvents.flatMap(e => 
    (e.jobs || []).filter(j => j.status === 'Done Reported').map(j => ({ event: e, job: j }))
  );

  return (
    <div className="space-y-6">
      {/* Top Banner: Member Context & Standing */}
      <div className="bg-navy text-white rounded-2xl p-6 shadow-md border border-[#1e2d42] flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold bg-gold text-navy px-2.5 py-0.5 rounded">
              {currentMember?.role || 'Brother'}
            </span>
            <span className="text-xs text-slate-300">
              {currentMember?.standing || 'Good Standing'}
            </span>
          </div>
          <h1 className="text-2xl font-display font-extrabold text-white tracking-tight">
            Welcome back, {currentMemberName}
          </h1>
          <p className="text-xs text-slate-300">
            Alpha Chapter &bull; {safeMembers.length} members
          </p>
        </div>

        {/* Quick Brother Actions */}
        <div className="flex flex-wrap items-center gap-3">
          {!isOfficer && currentMember && currentMember.duesBalance > 0 && (
            <button
              onClick={onPayDuesQuick}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg transition-all flex items-center gap-2 cursor-pointer shadow-xs"
            >
              <CreditCard className="w-4 h-4" />
              Pay Balance (${currentMember.duesBalance})
            </button>
          )}

          {isOfficer && (
            <button
              onClick={() => onNavigateTab('events')}
              className="bg-gold hover:bg-[#c5a02b] text-navy font-bold text-xs px-4 py-2.5 min-h-11 rounded-lg transition-all flex items-center gap-2 cursor-pointer shadow-xs"
            >
              <Calendar className="w-4 h-4" />
              Schedule Event
            </button>
          )}
        </div>
      </div>

      {/* KPI Stats Grid (officers) */}
      {isOfficer ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">Active roster</span>
              <Users className="w-4 h-4 text-blue-600" />
            </div>
            <div className="text-2xl font-display font-black text-slate-900">{activeMembersCount}</div>
          </div>

          <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">Avg attendance</span>
              <CheckCircle2 className="w-4 h-4 text-slate-500" />
            </div>
            <div className="text-2xl font-display font-black text-slate-900">{avgAttendance}%</div>
          </div>

          <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">Chapter receivables</span>
              <DollarSign className="w-4 h-4 text-amber-600" />
            </div>
            <div className="text-2xl font-display font-black text-slate-900">
              {formatMoney(totalReceivablesCents)}
            </div>
          </div>

          <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">Open jobs</span>
              <CheckSquare className="w-4 h-4 text-purple-600" />
            </div>
            <div className="text-2xl font-display font-black text-slate-900">{pendingTasks}</div>
          </div>
        </div>
      ) : (
        currentMember && (
          <div className="grid grid-cols-3 gap-4 bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
            <div className="space-y-0.5">
              <span className="text-xs font-medium text-slate-600 block">My balance</span>
              <span className={`text-lg font-display font-black ${currentMember.duesBalance > 0 ? 'text-red-600' : 'text-emerald-600'}`}>
                {formatMoney(currentMember.duesBalanceCents || Math.round((currentMember.duesBalance || 0) * 100))}
              </span>
            </div>
            <div className="space-y-0.5">
              <span className="text-xs font-medium text-slate-600 block">My attendance</span>
              <span className="text-lg font-display font-black text-slate-900">{currentMember.attendanceRate}%</span>
            </div>
            <div className="space-y-0.5">
              <span className="text-xs font-medium text-slate-600 block">My jobs</span>
              <span className="text-lg font-display font-black text-slate-900">{myClaimedJobs}</span>
            </div>
          </div>
        )
      )}

      {/* Officer Alert: Pending Job Sign-offs */}
      {isOfficer && pendingJobSignOffs.length > 0 && (
        <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-200/80 flex items-center justify-center text-amber-900 shrink-0">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h4 className="font-bold text-xs text-amber-950">
                {pendingJobSignOffs.length} Event Job{pendingJobSignOffs.length > 1 ? 's' : ''} Awaiting Supervisor Sign-Off
              </h4>
              <p className="text-xs text-amber-900">
                Brothers have completed duties on site and reported done. Review and approve or provide feedback.
              </p>
            </div>
          </div>

          <button
            onClick={() => onNavigateTab('events')}
            className="text-xs bg-navy hover:bg-slate-800 text-gold font-bold px-3.5 py-2 rounded-lg transition-all cursor-pointer shrink-0"
          >
            Review Jobs in Events
          </button>
        </div>
      )}

      {/* Main Grid: Upcoming Events & Chapter Initiatives */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        
        {/* Left 2 Cols: Upcoming Chapter Operations */}
        <div className="lg:col-span-2 space-y-4">
          <Card className="p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="font-display font-extrabold text-slate-900 text-base flex items-center gap-2">
                  <Calendar className="w-4 h-4 text-gold" />
                  Upcoming Chapter Operations
                </h3>
                <p className="text-xs text-slate-500">Upcoming mandatory meetings, brotherhood, and service events.</p>
              </div>

              <button
                onClick={() => onNavigateTab('events')}
                className="text-xs font-semibold text-navy hover:text-gold-muted flex items-center gap-1 cursor-pointer"
              >
                View All Events &rarr;
              </button>
            </div>

            {/* Event cards */}
            <div className="space-y-3">
              {upcomingEvents.length === 0 && (
                <p className="text-xs text-slate-500">No upcoming events.</p>
              )}
              {upcomingEvents.map(event => {
                const orgs = event.organizers || [];
                // Names only arrive with the Events detail fetch; the count is on the list row.
                const orgCount = event.organizerCount ?? orgs.length;
                const hasNoOrganizers = orgCount === 0;
                const eventJobs = event.jobs || [];
                const openJobs = eventJobs.filter(j => (j.claimants || []).length < (j.peopleNeeded || 1)).length;

                return (
                  <div 
                    key={event.id}
                    className="p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-white hover:border-gold transition-all space-y-2"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-amber-900 bg-amber-50 px-2 py-0.5 rounded border border-amber-200/50">
                            {event.type}
                          </span>
                          {event.required && (
                            <span className="text-xs font-extrabold bg-red-50 text-red-700 px-1.5 py-0.5 rounded border border-red-200">
                              Mandatory
                            </span>
                          )}
                        </div>
                        <h4 className="font-bold text-sm text-slate-900">{event.title}</h4>
                      </div>

                      <div className="text-right text-xs text-slate-500">
                        <span className="font-bold text-slate-800 block">{event.date}</span>
                        <span>{event.time}</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200/60">
                      <div className="flex flex-wrap items-center gap-2">
                        {hasNoOrganizers ? (
                          <span className="text-xs font-semibold bg-red-100 text-red-800 px-2 py-0.5 rounded flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3 text-red-600" />
                            Organizers needed
                          </span>
                        ) : (
                          <span className="text-xs text-slate-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                            Chairs: {orgs.length ? orgs.join(', ') : `${orgCount} chair${orgCount > 1 ? 's' : ''}`}
                          </span>
                        )}

                        {openJobs > 0 && (
                          <span className="text-xs text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                            {openJobs} Open Job{openJobs > 1 ? 's' : ''}
                          </span>
                        )}
                      </div>

                      {hasNoOrganizers && (
                        <button
                          onClick={() => onVolunteerOrganizer(event.id, currentMemberName)}
                          className="text-xs bg-gold hover:bg-[#c5a02b] text-navy font-bold px-2.5 py-1 rounded-md transition-all cursor-pointer shadow-2xs"
                        >
                          Volunteer as Organizer
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* Chair Initiatives Strip */}
          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 className="font-display font-extrabold text-slate-900 text-base flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-600" />
                Active Committee Initiatives
              </h3>
              <button
                onClick={() => onNavigateTab('initiatives')}
                className="text-xs font-semibold text-purple-700 hover:text-purple-900 cursor-pointer"
              >
                All Initiatives &rarr;
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {safeInitiatives.map(init => (
                <div key={init.id} className="p-3 bg-purple-50/40 rounded-xl border border-purple-100 space-y-1.5">
                  <div className="flex justify-between items-start">
                    <span className="text-xs font-bold text-purple-800 bg-purple-100 px-2 py-0.5 rounded">
                      {init.category}
                    </span>
                    <span className="text-xs text-slate-500">Target: {(init.targetDate || '').substring(5)}</span>
                  </div>
                  <h4 className="font-bold text-xs text-slate-900">{init.title}</h4>
                  <p className="text-xs text-slate-500 line-clamp-1">{init.description}</p>
                  <span className="text-xs text-purple-700 block font-semibold">
                    Leads: {(init.leadChairs || []).join(', ')}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Right 1 Col: Broadcasts & Chapter Feed */}
        <div className="space-y-4">
          {/* Executive Announcements */}
          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 className="font-display font-extrabold text-slate-900 text-sm flex items-center gap-2">
                <Megaphone className="w-4 h-4 text-blue-600" />
                Executive Chapter Broadcasts
              </h3>
            </div>

            <div className="space-y-3">
              {safeAnnouncements.length === 0 && (
                <p className="text-xs text-slate-500">No announcements yet.</p>
              )}
              {safeAnnouncements.map(a => (
                <div key={a.id} className="p-3 bg-blue-50/50 rounded-xl border border-blue-100 space-y-1">
                  <div className="flex justify-between items-center">
                    <span className="font-bold text-xs text-blue-950">{a.title}</span>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs bg-blue-200 text-blue-900 px-1.5 rounded font-bold">
                        {a.priority}
                      </span>
                      {isOfficer && (
                        <button
                          onClick={() => setPendingDelete(a)}
                          title="Remove from calendar"
                          aria-label={`Remove announcement "${a.title}" from calendar`}
                          className="text-blue-400 hover:text-red-600 cursor-pointer"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                  <p className="text-xs text-blue-900 leading-relaxed">{a.content}</p>
                  <div className="text-xs text-blue-600 pt-1">
                    {a.date} &bull; {a.author}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* Jobs */}
          <Card className="p-5 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h3 className="font-display font-extrabold text-slate-900 text-sm flex items-center gap-2">
                <CheckSquare className="w-4 h-4 text-gold" />
                Jobs
              </h3>
              <button
                onClick={() => onNavigateTab('tasks')}
                className="text-xs font-semibold text-slate-600 hover:text-slate-900 cursor-pointer"
              >
                View &rarr;
              </button>
            </div>

            <div className="space-y-2">
              {safeTasks.length === 0 && (
                <p className="text-xs text-slate-500">No jobs yet.</p>
              )}
              {safeTasks.slice(0, 3).map(task => (
                <div key={task.id} className="p-2.5 rounded-lg border border-slate-100 bg-slate-50 flex items-center justify-between text-xs">
                  <div>
                    <div className="font-bold text-slate-800">{task.title}</div>
                    <div className="text-xs text-slate-500">Assigned: {task.assignedTo}</div>
                  </div>
                  <span className={`text-xs font-bold px-1.5 py-0.5 rounded ${
                    task.status === 'Completed' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                  }`}>
                    {task.status}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>

      </div>

      {pendingDelete && (
        <ConfirmDialog
          title="Remove announcement?"
          tone="danger"
          body={<p>"<strong>{pendingDelete.title}</strong>" comes off the calendar for everyone. Already-sent messages are not recalled.</p>}
          confirmLabel="Remove"
          onCancel={() => setPendingDelete(null)}
          onConfirm={() => { onDeleteAnnouncement(pendingDelete.id); setPendingDelete(null); }}
        />
      )}
    </div>
  );
}
